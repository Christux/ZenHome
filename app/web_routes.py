"""Additional routes used by the ZenHome views."""

from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse
from sqlalchemy import case, delete, func, select
from sqlalchemy.orm import Session

from .business import (
    ChecklistInput,
    ItemCreate,
    ItemStatusUpdate,
    ItemUpdate,
    NotificationConfigInput,
    RuleInput,
    ScheduleInput,
    StatusInput,
)
from .database import get_session
from .globals import PROJECT_DIR, ZENHOME_ENV
from .models import (
    ChecklistItems,
    ItemStatuses,
    ItemTypes,
    Items,
    NotificationConfigs,
    NotificationStatuses,
    Notifications,
    OccurrenceStatuses,
    RecurrenceRuleWeekdays,
    RecurrenceRules,
    RecurrenceTypes,
    ScheduleOccurrences,
    Schedules,
    Users,
)

router = APIRouter(prefix="/api", tags=["interface web"])
public_router = APIRouter(tags=["interface web"])


def as_dict(instance: object) -> dict[str, Any]:
    """Converts a SQLAlchemy row into a dictionary usable by the API."""
    return {column.key: getattr(instance, column.key) for column in instance.__table__.columns}


def require(session: Session, model: type, entity_id: int, label: str) -> object:
    """Fetches an entity or raises an HTTP 404 if it does not exist."""
    instance = session.get(model, entity_id)
    if instance is None:
        raise HTTPException(404, f"{label} not found.")
    return instance


def dictionary_id(session: Session, model: type, code: str) -> int:
    """Fetches the active dictionary entry ID from its code."""
    instance = session.scalar(select(model).where(model.code == code, model.is_active.is_(True)))
    if instance is None:
        raise HTTPException(400, "Invalid dictionary value.")
    return instance.id


def serialize_item(item: Items) -> dict[str, Any]:
    """Prepares the public representation of an item with its related metadata."""
    return {
        "id": item.id,
        "title": item.title,
        "content": item.content,
        "is_favorite": item.is_favorite,
        "is_archived": item.is_archived,
        "created_at": item.created_at,
        "updated_at": item.updated_at,
        "type_code": item.type.code,
        "type_label": item.type.label,
        "status_code": item.status.code,
        "status_label": item.status.label,
    }


def fetch_item(item_id: int, db: Session) -> dict[str, Any]:
    """Fetches and serializes an item, raising a 404 if it does not exist."""
    item = db.scalar(select(Items).where(Items.id == item_id))
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found.")
    return serialize_item(item)


@public_router.get("/", include_in_schema=False)
def home() -> FileResponse:
    """Returns the application's HTML landing page."""
    return FileResponse(PROJECT_DIR / "index.html")


@public_router.get("/item/{item_id}", include_in_schema=False)
def item_page(item_id: int) -> FileResponse:
    """Returns the application shell for a permanent item URL."""
    if item_id < 1:
        raise HTTPException(status_code=404, detail="Item not found.")
    return FileResponse(PROJECT_DIR / "index.html")


@public_router.get("/{page}", include_in_schema=False)
def web_page(page: str) -> FileResponse:
    """Returns the requested SPA page based on the navigation URL."""
    if page not in {"notes", "checklists", "tasks", "kanban", "calendar"}:
        raise HTTPException(status_code=404, detail="Page not found.")
    return FileResponse(PROJECT_DIR / "index.html")


@public_router.get("/api/health")
def health() -> dict[str, str]:
    """Checks whether the service is responding correctly."""
    return {"status": "ok"}


if ZENHOME_ENV == "development":
    @public_router.get("/api/dev/version")
    def development_version() -> dict[str, str]:
        """Returns a version that changes when development files are edited."""
        watched_files = [PROJECT_DIR / "index.html"]
        watched_files.extend(path for path in (PROJECT_DIR / "app").rglob("*.py") if path.is_file())
        watched_files.extend(
            path for path in (PROJECT_DIR / "static").rglob("*")
            if path.is_file() and not path.name.startswith(".")
        )
        signature = "|".join(
            f"{path.relative_to(PROJECT_DIR)}:{path.stat().st_mtime_ns}:{path.stat().st_size}"
            for path in sorted(watched_files)
        )
        return {"signature": signature}


@public_router.get("/api/items")
def list_items(
    item_type: Literal["NOTE", "CHECKLIST", "TASK"] | None = Query(default=None),
    include_archived: bool = Query(default=False),
    db: Session = Depends(get_session),
) -> list[dict[str, Any]]:
    """Lists the items visible to the demo user."""
    query = select(Items).join(Items.user).join(Items.type).where(Users.email == "demo@zenhome.local")
    if item_type:
        query = query.where(ItemTypes.code == item_type)
    if not include_archived:
        query = query.where(Items.is_archived.is_(False))
    items = db.scalars(query.order_by(Items.created_at.desc(), Items.id.desc())).all()
    return [serialize_item(item) for item in items]


@public_router.post("/api/items", status_code=status.HTTP_201_CREATED)
def create_item(payload: ItemCreate, db: Session = Depends(get_session)) -> dict[str, Any]:
    """Creates a new business item from the validated payload."""
    user = db.scalar(select(Users).where(Users.email == "demo@zenhome.local"))
    item_type = db.scalar(select(ItemTypes).where(ItemTypes.code == payload.type_code, ItemTypes.is_active.is_(True)))
    item_status = db.scalar(select(ItemStatuses).where(ItemStatuses.code == payload.status_code, ItemStatuses.is_active.is_(True)))
    if user is None or item_type is None or item_status is None:
        raise HTTPException(status_code=500, detail="Dictionaries not initialized.")
    item = Items(
        user_id=user.id,
        type_id=item_type.id,
        status_id=item_status.id,
        title=payload.title.strip(),
        content=payload.content,
    )
    db.add(item)
    db.flush()
    if payload.checklist_items and payload.type_code != "CHECKLIST":
        raise HTTPException(status_code=422, detail="Checklist rows require a checklist item.")
    for position, checklist_item in enumerate(payload.checklist_items):
        db.add(ChecklistItems(
            item_id=item.id,
            label=checklist_item.label.strip(),
            position=checklist_item.position if checklist_item.position is not None else position,
            is_checked=bool(checklist_item.is_checked),
        ))
    return fetch_item(item.id, db)


@public_router.patch("/api/items/{item_id}")
def update_item(item_id: int, payload: ItemUpdate, db: Session = Depends(get_session)) -> dict[str, Any]:
    """Updates the editable fields of an existing item."""
    item = db.get(Items, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found.")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(item, field, value)
    item.updated_at = datetime.now().isoformat(timespec="seconds")
    return serialize_item(item)


@public_router.delete("/api/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_item(item_id: int, db: Session = Depends(get_session)) -> None:
    """Deletes an existing item and its related data."""
    item = db.get(Items, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found.")
    schedule_ids = select(Schedules.id).where(Schedules.item_id == item_id)
    occurrence_ids = select(ScheduleOccurrences.id).where(ScheduleOccurrences.schedule_id.in_(schedule_ids))
    notification_config_ids = select(NotificationConfigs.id).where(NotificationConfigs.item_id == item_id)
    db.execute(delete(Notifications).where(
        Notifications.schedule_occurrence_id.in_(occurrence_ids)
        | Notifications.notification_config_id.in_(notification_config_ids)
    ))
    db.execute(delete(ScheduleOccurrences).where(ScheduleOccurrences.schedule_id.in_(schedule_ids)))
    db.execute(delete(Schedules).where(Schedules.item_id == item_id))
    db.execute(delete(NotificationConfigs).where(NotificationConfigs.item_id == item_id))
    db.execute(delete(ChecklistItems).where(ChecklistItems.item_id == item_id))
    db.execute(delete(Items).where(Items.id == item_id))


@public_router.patch("/api/items/{item_id}/status")
def update_item_status(item_id: int, payload: ItemStatusUpdate, db: Session = Depends(get_session)) -> dict[str, Any]:
    """Updates the status of a business item."""
    item = db.get(Items, item_id)
    new_status = db.scalar(select(ItemStatuses).where(ItemStatuses.code == payload.status_code, ItemStatuses.is_active.is_(True)))
    if new_status is None:
        raise HTTPException(status_code=400, detail="Invalid status.")
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found.")
    item.status_id = new_status.id
    item.updated_at = datetime.now().isoformat(timespec="seconds")
    return serialize_item(item)


@router.get("/dashboard")
def dashboard(db: Session = Depends(get_session)) -> dict[str, Any]:
    """Returns a summary of counters and upcoming occurrences."""
    counts = db.execute(
        select(
            func.sum(case((ItemTypes.code == "TASK", 1), else_=0)).label("tasks_total"),
            func.sum(case(((ItemTypes.code == "TASK") & (ItemStatuses.code == "DONE"), 1), else_=0)).label("tasks_done"),
            func.sum(case(((ItemTypes.code == "CHECKLIST") & ~ItemStatuses.code.in_(["DONE", "CANCELLED"]), 1), else_=0)).label("checklists_open"),
        )
        .select_from(Items)
        .join(Items.user)
        .join(Items.status)
        .join(Items.type)
        .where(Users.email == "demo@zenhome.local", Items.is_archived.is_(False))
    ).mappings().one()
    today_count = db.scalar(
        select(func.count(ScheduleOccurrences.id))
        .join(ScheduleOccurrences.schedule)
        .join(Schedules.item)
        .join(Items.user)
        .join(ScheduleOccurrences.status)
        .where(
            Users.email == "demo@zenhome.local",
            Items.is_archived.is_(False),
            OccurrenceStatuses.code == "PENDING",
            func.date(ScheduleOccurrences.starts_at) == func.date("now"),
        )
    ) or 0
    upcoming = db.execute(
        select(
            ScheduleOccurrences.id,
            ScheduleOccurrences.starts_at,
            Items.id.label("item_id"),
            Items.title,
            ItemTypes.code.label("type_code"),
        )
        .join(ScheduleOccurrences.schedule)
        .join(Schedules.item)
        .join(Items.type)
        .join(Items.user)
        .join(ScheduleOccurrences.status)
        .where(Users.email == "demo@zenhome.local", Items.is_archived.is_(False), OccurrenceStatuses.code == "PENDING")
        .where(ScheduleOccurrences.starts_at >= func.datetime("now"))
        .order_by(ScheduleOccurrences.starts_at)
        .limit(10)
    ).mappings().all()
    return {
        "counts": {**dict(counts), "today": today_count},
        "upcoming_occurrences": [dict(row) for row in upcoming],
    }


@router.get("/dictionaries/{name}")
def dictionaries(name: str, db: Session = Depends(get_session)) -> list[dict[str, Any]]:
    """Returns the active values from a business dictionary."""
    models = {
        "item-types": ItemTypes,
        "item-statuses": ItemStatuses,
        "recurrence-types": RecurrenceTypes,
        "occurrence-statuses": OccurrenceStatuses,
        "notification-statuses": NotificationStatuses,
    }
    model = models.get(name)
    if model is None:
        raise HTTPException(404, "Dictionary not found.")
    rows = db.scalars(select(model).where(model.is_active.is_(True)).order_by(model.sort_order)).all()
    return [{key: getattr(row, key) for key in ("id", "code", "label", "sort_order")} for row in rows]


@router.get("/items/{item_id}/detail")
def item_detail(item_id: int, db: Session = Depends(get_session)) -> dict[str, Any]:
    """Fetches the complete detail for an item, including its checklist and schedules."""
    item = require(db, Items, item_id, "Item")
    result = as_dict(item)
    result.update(serialize_item(item))
    result["checklist_items"] = [as_dict(row) for row in sorted(item.checklist_items, key=lambda row: (row.position, row.id))]
    result["schedules"] = [as_dict(row) for row in sorted(item.schedules, key=lambda row: row.start_at)]
    result["notification_configs"] = [as_dict(row) for row in item.notification_configs]
    return result


@router.post("/items/{item_id}/checklist-items", status_code=status.HTTP_201_CREATED)
def add_checklist_item(item_id: int, body: ChecklistInput, db: Session = Depends(get_session)) -> dict[str, Any]:
    """Adds a checklist row to an existing item."""
    require(db, Items, item_id, "Item")
    position = body.position
    if position is None:
        position = db.scalar(select(func.coalesce(func.max(ChecklistItems.position), -1) + 1).where(ChecklistItems.item_id == item_id)) or 0
    row = ChecklistItems(item_id=item_id, label=body.label, position=position, is_checked=bool(body.is_checked))
    db.add(row)
    db.flush()
    return as_dict(row)


@router.post("/items/{item_id}/checklist-items/reset")
def reset_checklist(item_id: int, db: Session = Depends(get_session)) -> dict[str, int]:
    """Resets all checked rows in a checklist."""
    item = require(db, Items, item_id, "Checklist")
    reset_count = 0
    for row in item.checklist_items:
        if row.is_checked or row.checked_at is not None:
            row.is_checked = False
            row.checked_at = None
            reset_count += 1
    return {"item_id": item_id, "reset_count": reset_count}


@router.patch("/checklist-items/{checklist_item_id}")
def edit_checklist_item(checklist_item_id: int, body: ChecklistInput, db: Session = Depends(get_session)) -> dict[str, Any]:
    """Updates the label and state of a checklist row."""
    row = require(db, ChecklistItems, checklist_item_id, "Checklist row")
    row.label = body.label
    if body.position is not None:
        row.position = body.position
    if body.is_checked is not None:
        row.is_checked = body.is_checked
        row.checked_at = datetime.now().isoformat(timespec="seconds") if body.is_checked else None
    return as_dict(row)


@router.delete("/checklist-items/{checklist_item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_checklist_item(checklist_item_id: int, db: Session = Depends(get_session)) -> None:
    """Deletes an existing checklist row."""
    if db.execute(delete(ChecklistItems).where(ChecklistItems.id == checklist_item_id)).rowcount == 0:
        raise HTTPException(404, "Checklist row not found.")


@router.get("/recurrence-rules")
def recurrence_rules(db: Session = Depends(get_session)) -> list[dict[str, Any]]:
    """Returns the list of available recurrence rules."""
    rules = db.scalars(select(RecurrenceRules).order_by(RecurrenceRules.label)).all()
    return [{**as_dict(rule), "recurrence_type_code": rule.recurrence_type.code,
             "weekdays": [row.weekday for row in sorted(rule.recurrence_rule_weekdays, key=lambda row: row.weekday)]}
            for rule in rules]


@router.post("/recurrence-rules", status_code=status.HTTP_201_CREATED)
def add_rule(body: RuleInput, db: Session = Depends(get_session)) -> dict[str, int]:
    """Creates a recurrence rule and its selected weekdays."""
    if any(day not in range(1, 8) for day in body.weekdays):
        raise HTTPException(422, "Days must be between 1 and 7.")
    rule = RecurrenceRules(
        recurrence_type_id=dictionary_id(db, RecurrenceTypes, body.recurrence_type_code),
        label=body.label,
        expression=body.expression,
        day_of_month=body.day_of_month,
        month_of_year=body.month_of_year,
    )
    rule.recurrence_rule_weekdays = [RecurrenceRuleWeekdays(weekday=day) for day in set(body.weekdays)]
    db.add(rule)
    db.flush()
    return {"id": rule.id}


@router.delete("/recurrence-rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_rule(rule_id: int, db: Session = Depends(get_session)) -> None:
    """Deletes an existing recurrence rule."""
    if db.execute(delete(RecurrenceRules).where(RecurrenceRules.id == rule_id)).rowcount == 0:
        raise HTTPException(404, "Recurrence rule not found.")


@router.get("/items/{item_id}/schedules")
def schedules(item_id: int, db: Session = Depends(get_session)) -> list[dict[str, Any]]:
    """Lists the schedules associated with an item."""
    item = require(db, Items, item_id, "Item")
    return [{**as_dict(row), "recurrence_label": row.recurrence_rule.label if row.recurrence_rule else None}
            for row in sorted(item.schedules, key=lambda row: row.start_at)]


@router.post("/items/{item_id}/schedules", status_code=status.HTTP_201_CREATED)
def add_schedule(item_id: int, body: ScheduleInput, db: Session = Depends(get_session)) -> dict[str, Any]:
    """Adds a recurrence schedule to an item."""
    require(db, Items, item_id, "Item")
    if body.recurrence_rule_id is not None:
        require(db, RecurrenceRules, body.recurrence_rule_id, "Recurrence rule")
    row = Schedules(item_id=item_id, recurrence_rule_id=body.recurrence_rule_id, start_at=body.start_at, end_at=body.end_at, is_active=body.is_active)
    db.add(row)
    db.flush()
    return as_dict(row)


@router.delete("/schedules/{schedule_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_schedule(schedule_id: int, db: Session = Depends(get_session)) -> None:
    """Deletes an existing schedule."""
    if db.execute(delete(Schedules).where(Schedules.id == schedule_id)).rowcount == 0:
        raise HTTPException(404, "Schedule not found.")


@router.get("/occurrences")
def occurrences(start_at: str | None = None, end_at: str | None = None, db: Session = Depends(get_session)) -> list[dict[str, Any]]:
    """Returns occurrences filtered by period."""
    query = select(
        ScheduleOccurrences,
        Items.id.label("item_id"),
        Items.title.label("item_title"),
        ItemTypes.code.label("type_code"),
        OccurrenceStatuses.code.label("status_code"),
    ).join(ScheduleOccurrences.schedule).join(Schedules.item).join(Items.type).join(ScheduleOccurrences.status)
    if start_at:
        query = query.where(ScheduleOccurrences.starts_at >= start_at)
    if end_at:
        query = query.where(ScheduleOccurrences.starts_at <= end_at)
    rows = db.execute(query.order_by(ScheduleOccurrences.starts_at)).all()
    return [{
        **as_dict(row[0]),
        "item_id": row.item_id,
        "item_title": row.item_title,
        "type_code": row.type_code,
        "status_code": row.status_code,
    } for row in rows]


@router.patch("/occurrences/{occurrence_id}/status")
def update_occurrence(occurrence_id: int, body: StatusInput, db: Session = Depends(get_session)) -> dict[str, Any]:
    """Updates the status of a scheduled occurrence."""
    row = require(db, ScheduleOccurrences, occurrence_id, "Occurrence")
    row.status_id = dictionary_id(db, OccurrenceStatuses, body.code)
    row.completed_at = datetime.now().isoformat(timespec="seconds") if body.code == "COMPLETED" else None
    return as_dict(row)


@router.get("/items/{item_id}/notification-configs")
def notification_configs(item_id: int, db: Session = Depends(get_session)) -> list[dict[str, Any]]:
    """Lists the notification configurations for an item."""
    item = require(db, Items, item_id, "Item")
    return [as_dict(row) for row in item.notification_configs]


@router.post("/items/{item_id}/notification-configs", status_code=status.HTTP_201_CREATED)
def add_notification_config(item_id: int, body: NotificationConfigInput, db: Session = Depends(get_session)) -> dict[str, Any]:
    """Creates a notification configuration for an item."""
    require(db, Items, item_id, "Item")
    row = NotificationConfigs(item_id=item_id, label=body.label, offset_minutes=body.offset_minutes, is_enabled=body.is_enabled)
    db.add(row)
    db.flush()
    return as_dict(row)


@router.get("/notifications")
def notifications(status_code: str | None = Query(default=None), db: Session = Depends(get_session)) -> list[dict[str, Any]]:
    """Returns notifications filtered by status."""
    query = select(Notifications, Items.title.label("item_title"), NotificationStatuses.code.label("status_code")) \
        .join(Notifications.status).join(Notifications.schedule_occurrence).join(ScheduleOccurrences.schedule).join(Schedules.item)
    if status_code:
        query = query.where(NotificationStatuses.code == status_code)
    rows = db.execute(query.order_by(Notifications.notify_at)).all()
    return [{**as_dict(row[0]), "item_title": row.item_title, "status_code": row.status_code} for row in rows]


@router.patch("/notifications/{notification_id}/status")
def update_notification(notification_id: int, body: StatusInput, db: Session = Depends(get_session)) -> dict[str, Any]:
    """Updates the status of an existing notification."""
    row = require(db, Notifications, notification_id, "Notification")
    row.status_id = dictionary_id(db, NotificationStatuses, body.code)
    row.sent_at = datetime.now().isoformat(timespec="seconds") if body.code == "SENT" else None
    row.error_message = body.error_message
    return as_dict(row)
