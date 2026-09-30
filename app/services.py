"""Functional operations for the ZenHome API, independent from HTTP routing."""

from datetime import datetime, timezone
from typing import Any, Literal

from sqlalchemy import case, delete, func, select
from sqlalchemy.orm import Session
from sqlalchemy.sql.functions import count

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
from .daemon import create_occurrences
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
)


class ServiceError(Exception):
    """Business failure translated to an HTTP response at the application edge."""

    def __init__(self, status_code: int, detail: str) -> None:
        """Initialize the error with its HTTP status and public detail."""
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def _utc_now_iso() -> str:
    """Return the current timestamp with an explicit UTC offset."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def as_dict(instance: object) -> dict[str, Any]:
    """Converts a SQLAlchemy row into a dictionary usable by the API."""
    return {column.key: getattr(instance, column.key) for column in instance.__table__.columns}


def require(session: Session, model: type, entity_id: int, label: str) -> object:
    """Return an entity by ID or raise a not-found service error."""
    instance = session.get(model, entity_id)
    if instance is None:
        raise ServiceError(404, f"{label} not found.")
    return instance


def require_accessible_item(session: Session, user_id: int, item_id: int, label: str = "Item") -> Items:
    """Return an item owned by the user or shared with them."""
    item = session.scalar(select(Items).where(
        Items.id == item_id,
        (Items.user_id == user_id) | (Items.is_private.is_(False)),
    ))
    if item is None:
        raise ServiceError(404, f"{label} not found.")
    return item


def require_owned_item(session: Session, user_id: int, item_id: int, label: str = "Item") -> Items:
    """Return an item owned by the user or raise a not-found service error."""
    item = session.scalar(select(Items).where(Items.id == item_id, Items.user_id == user_id))
    if item is None:
        raise ServiceError(404, f"{label} not found.")
    return item


def dictionary_id(session: Session, model: type, code: str) -> int:
    """Return the ID of an active dictionary value matching its code."""
    instance = session.scalar(select(model).where(model.code == code, model.is_active.is_(True)))
    if instance is None:
        raise ServiceError(400, "Invalid dictionary value.")
    return instance.id


def serialize_item(item: Items, user_id: int) -> dict[str, Any]:
    """Build the public representation of an item and its metadata."""
    return {
        "id": item.id,
        "title": item.title,
        "content": item.content,
        "is_favorite": item.is_favorite,
        "is_archived": item.is_archived,
        "is_private": item.is_private,
        "is_owner": item.user_id == user_id,
        "created_at": item.created_at,
        "updated_at": item.updated_at,
        "type_code": item.type.code,
        "type_label": item.type.label,
        "status_code": item.status.code,
        "status_label": item.status.label,
    }


def list_items(
    user_id: int,
    session: Session,
    item_type: Literal["NOTE", "CHECKLIST", "TASK"] | None = None,
    include_archived: bool = False,
) -> list[dict[str, Any]]:
    """List a user's items with optional type and archive filters."""
    query = select(Items).join(Items.type).where(
        (Items.user_id == user_id) | (Items.is_private.is_(False))
    )
    if item_type:
        query = query.where(ItemTypes.code == item_type)
    if not include_archived:
        query = query.where(Items.is_archived.is_(False))
    items = session.scalars(query.order_by(Items.created_at.desc(), Items.id.desc())).all()
    return [serialize_item(item, user_id) for item in items]


def create_item(user_id: int, payload: ItemCreate, session: Session) -> dict[str, Any]:
    """Create an item and any validated checklist rows for its owner."""
    item_type = session.scalar(select(ItemTypes).where(ItemTypes.code == payload.type_code, ItemTypes.is_active.is_(True)))
    item_status = session.scalar(select(ItemStatuses).where(ItemStatuses.code == payload.status_code, ItemStatuses.is_active.is_(True)))
    if item_type is None or item_status is None:
        raise ServiceError(500, "Dictionaries not initialized.")
    if payload.checklist_items and payload.type_code != "CHECKLIST":
        raise ServiceError(422, "Checklist rows require a checklist item.")
    item = Items(
        user_id=user_id,
        type_id=item_type.id,
        status_id=item_status.id,
        title=payload.title.strip(),
        content=payload.content,
        is_private=payload.is_private,
    )
    session.add(item)
    session.flush()
    for position, checklist_item in enumerate(payload.checklist_items):
        session.add(ChecklistItems(
            item_id=item.id,
            label=checklist_item.label.strip(),
            position=checklist_item.position if checklist_item.position is not None else position,
            is_checked=bool(checklist_item.is_checked),
        ))
    for notification_config in payload.notification_configs:
        session.add(NotificationConfigs(
            item_id=item.id,
            label=notification_config.label,
            offset_minutes=notification_config.offset_minutes,
            is_enabled=notification_config.is_enabled,
        ))
    return serialize_item(item, user_id)


def update_item(user_id: int, item_id: int, payload: ItemUpdate, session: Session) -> dict[str, Any]:
    """Update an accessible item, restricting privacy changes to its owner."""
    item = require_accessible_item(session, user_id, item_id)
    if "is_private" in payload.model_fields_set and item.user_id != user_id:
        raise ServiceError(403, "Only the item creator can change its privacy.")
    values = payload.model_dump(exclude_unset=True, exclude={"notification_configs"})
    configs_to_replace = payload.notification_configs if "notification_configs" in payload.model_fields_set else None
    for field, value in values.items():
        setattr(item, field, value)
    if configs_to_replace is not None:
        config_ids = select(NotificationConfigs.id).where(NotificationConfigs.item_id == item_id)
        session.execute(delete(Notifications).where(Notifications.notification_config_id.in_(config_ids)))
        session.execute(delete(NotificationConfigs).where(NotificationConfigs.item_id == item_id))
        for notification_config in configs_to_replace:
            session.add(NotificationConfigs(
                item_id=item.id,
                label=notification_config.label,
                offset_minutes=notification_config.offset_minutes,
                is_enabled=notification_config.is_enabled,
            ))
    item.updated_at = _utc_now_iso()
    return serialize_item(item, user_id)


def delete_item(user_id: int, item_id: int, session: Session) -> None:
    """Delete a user's item and its dependent records."""
    require_owned_item(session, user_id, item_id)
    schedule_ids = select(Schedules.id).where(Schedules.item_id == item_id)
    occurrence_ids = select(ScheduleOccurrences.id).where(ScheduleOccurrences.schedule_id.in_(schedule_ids))
    notification_config_ids = select(NotificationConfigs.id).where(NotificationConfigs.item_id == item_id)
    session.execute(delete(Notifications).where(
        Notifications.schedule_occurrence_id.in_(occurrence_ids)
        | Notifications.notification_config_id.in_(notification_config_ids)
    ))
    session.execute(delete(ScheduleOccurrences).where(ScheduleOccurrences.schedule_id.in_(schedule_ids)))
    session.execute(delete(Schedules).where(Schedules.item_id == item_id))
    session.execute(delete(NotificationConfigs).where(NotificationConfigs.item_id == item_id))
    session.execute(delete(ChecklistItems).where(ChecklistItems.item_id == item_id))
    session.execute(delete(Items).where(Items.id == item_id))


def update_item_status(user_id: int, item_id: int, payload: ItemStatusUpdate, session: Session) -> dict[str, Any]:
    """Set the status of an item owned by the user."""
    item = require_accessible_item(session, user_id, item_id)
    new_status = session.scalar(select(ItemStatuses).where(ItemStatuses.code == payload.status_code, ItemStatuses.is_active.is_(True)))
    if new_status is None:
        raise ServiceError(400, "Invalid status.")
    if item is None:
        raise ServiceError(404, "Item not found.")
    item.status_id = new_status.id
    item.updated_at = _utc_now_iso()
    return serialize_item(item, user_id)


def dashboard(user_id: int, session: Session) -> dict[str, Any]:
    """Return the user's item counts and upcoming occurrences."""
    counts = session.execute(
        select(
            func.sum(case((ItemTypes.code == "TASK", 1), else_=0)).label("tasks_total"),
            func.sum(case(((ItemTypes.code == "TASK") & (ItemStatuses.code == "DONE"), 1), else_=0)).label("tasks_done"),
            func.sum(case(((ItemTypes.code == "CHECKLIST") & ~ItemStatuses.code.in_(["DONE", "CANCELLED"]), 1), else_=0)).label("checklists_open"),
        )
        .select_from(Items)
        .join(Items.user)
        .join(Items.status)
        .join(Items.type)
        .where(((Items.user_id == user_id) | (Items.is_private.is_(False))), Items.is_archived.is_(False))
    ).mappings().one()
    today_count = session.scalar(
        select(count(ScheduleOccurrences.id))
        .join(ScheduleOccurrences.schedule)
        .join(Schedules.item)
        .join(Items.user)
        .join(ScheduleOccurrences.status)
        .where(
            (Items.user_id == user_id) | (Items.is_private.is_(False)),
            Items.is_archived.is_(False),
            OccurrenceStatuses.code == "PENDING",
            func.date(ScheduleOccurrences.starts_at) == func.date("now"),
        )
    ) or 0
    upcoming = session.execute(
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
        .where(((Items.user_id == user_id) | (Items.is_private.is_(False))), Items.is_archived.is_(False), OccurrenceStatuses.code == "PENDING")
        .where(ScheduleOccurrences.starts_at >= func.datetime("now"))
        .order_by(ScheduleOccurrences.starts_at)
        .limit(10)
    ).mappings().all()
    return {
        "counts": {**dict(counts), "today": today_count},
        "upcoming_occurrences": [dict(row) for row in upcoming],
    }


def dictionaries(name: str, session: Session) -> list[dict[str, Any]]:
    """List active values from the named business dictionary."""
    models = {
        "item-types": ItemTypes,
        "item-statuses": ItemStatuses,
        "recurrence-types": RecurrenceTypes,
        "occurrence-statuses": OccurrenceStatuses,
        "notification-statuses": NotificationStatuses,
    }
    model = models.get(name)
    if model is None:
        raise ServiceError(404, "Dictionary not found.")
    rows = session.scalars(select(model).where(model.is_active.is_(True)).order_by(model.sort_order)).all()
    return [{key: getattr(row, key) for key in ("id", "code", "label", "sort_order")} for row in rows]


def item_detail(user_id: int, item_id: int, session: Session) -> dict[str, Any]:
    """Return an owned item with its checklist, schedules, and notifications."""
    item = require_accessible_item(session, user_id, item_id)
    result = as_dict(item)
    result.update(serialize_item(item, user_id))
    result["checklist_items"] = [as_dict(row) for row in sorted(item.checklist_items, key=lambda row: (row.position, row.id))]
    result["schedules"] = [as_dict(row) for row in sorted(item.schedules, key=lambda row: row.start_at)]
    result["notification_configs"] = [as_dict(row) for row in item.notification_configs]
    return result


def add_checklist_item(user_id: int, item_id: int, body: ChecklistInput, session: Session) -> dict[str, Any]:
    """Add a checklist row to an item owned by the user."""
    require_accessible_item(session, user_id, item_id)
    position = body.position
    if position is None:
        position = session.scalar(select(func.coalesce(func.max(ChecklistItems.position), -1) + 1).where(ChecklistItems.item_id == item_id)) or 0
    row = ChecklistItems(item_id=item_id, label=body.label, position=position, is_checked=bool(body.is_checked))
    session.add(row)
    session.flush()
    return as_dict(row)


def reset_checklist(user_id: int, item_id: int, session: Session) -> dict[str, int]:
    """Clear checked states from every row in an accessible checklist."""
    item = require_accessible_item(session, user_id, item_id, "Checklist")
    reset_count = 0
    for row in item.checklist_items:
        if row.is_checked or row.checked_at is not None:
            row.is_checked = False
            row.checked_at = None
            reset_count += 1
    return {"item_id": item_id, "reset_count": reset_count}


def edit_checklist_item(user_id: int, checklist_item_id: int, body: ChecklistInput, session: Session) -> dict[str, Any]:
    """Update a checklist row after verifying ownership of its parent item."""
    row = require(session, ChecklistItems, checklist_item_id, "Checklist row")
    require_accessible_item(session, user_id, row.item_id, "Checklist row")
    row.label = body.label
    if body.position is not None:
        row.position = body.position
    if body.is_checked is not None:
        row.is_checked = body.is_checked
        row.checked_at = _utc_now_iso() if body.is_checked else None
    return as_dict(row)


def delete_checklist_item(user_id: int, checklist_item_id: int, session: Session) -> None:
    """Delete a checklist row belonging to the user."""
    row = require(session, ChecklistItems, checklist_item_id, "Checklist row")
    require_accessible_item(session, user_id, row.item_id, "Checklist row")
    session.delete(row)


def recurrence_rules(session: Session) -> list[dict[str, Any]]:
    """List recurrence rules with their recurrence type and weekdays."""
    rules = session.scalars(select(RecurrenceRules).order_by(RecurrenceRules.label)).all()
    return [{**as_dict(rule), "recurrence_type_code": rule.recurrence_type.code,
             "weekdays": [row.weekday for row in sorted(rule.recurrence_rule_weekdays, key=lambda row: row.weekday)]}
            for rule in rules]


def add_rule(body: RuleInput, session: Session) -> dict[str, int]:
    """Create a recurrence rule and its selected weekdays."""
    if any(day not in range(1, 8) for day in body.weekdays):
        raise ServiceError(422, "Days must be between 1 and 7.")
    rule = RecurrenceRules(
        recurrence_type_id=dictionary_id(session, RecurrenceTypes, body.recurrence_type_code),
        label=body.label,
        expression=body.expression,
        day_of_month=body.day_of_month,
        month_of_year=body.month_of_year,
    )
    rule.recurrence_rule_weekdays = [RecurrenceRuleWeekdays(weekday=day) for day in set(body.weekdays)]
    session.add(rule)
    session.flush()
    return {"id": rule.id}


def delete_rule(rule_id: int, session: Session) -> None:
    """Delete a recurrence rule or raise an error when it is missing."""
    if session.execute(delete(RecurrenceRules).where(RecurrenceRules.id == rule_id)).rowcount == 0:
        raise ServiceError(404, "Recurrence rule not found.")


def schedules(user_id: int, item_id: int, session: Session) -> list[dict[str, Any]]:
    """List schedules attached to an item owned by the user."""
    item = require_accessible_item(session, user_id, item_id)
    return [{**as_dict(row), "recurrence_label": row.recurrence_rule.label if row.recurrence_rule else None}
            for row in sorted(item.schedules, key=lambda row: row.start_at)]


def add_schedule(user_id: int, item_id: int, body: ScheduleInput, session: Session) -> dict[str, Any]:
    """Add a schedule to an owned item and generate its occurrences."""
    require_accessible_item(session, user_id, item_id)
    if body.recurrence_rule_id is not None:
        require(session, RecurrenceRules, body.recurrence_rule_id, "Recurrence rule")
    row = Schedules(item_id=item_id, recurrence_rule_id=body.recurrence_rule_id, start_at=body.start_at, end_at=body.end_at, is_active=body.is_active)
    session.add(row)
    session.flush()
    create_occurrences(session)
    return as_dict(row)


def delete_schedule(user_id: int, schedule_id: int, session: Session) -> None:
    """Delete a schedule after checking ownership of its item."""
    schedule = require(session, Schedules, schedule_id, "Schedule")
    require_accessible_item(session, user_id, schedule.item_id, "Schedule")
    session.delete(schedule)


def occurrences(user_id: int, start_at: str | None, end_at: str | None, session: Session) -> list[dict[str, Any]]:
    """List the user's occurrences within an optional time range."""
    query = select(
        ScheduleOccurrences,
        Items.id.label("item_id"),
        Items.title.label("item_title"),
        ItemTypes.code.label("type_code"),
        OccurrenceStatuses.code.label("status_code"),
    ).join(ScheduleOccurrences.schedule).join(Schedules.item).join(Items.type).join(ScheduleOccurrences.status)
    query = query.where((Items.user_id == user_id) | (Items.is_private.is_(False)))
    if start_at:
        query = query.where(ScheduleOccurrences.starts_at >= start_at)
    if end_at:
        query = query.where(ScheduleOccurrences.starts_at <= end_at)
    rows = session.execute(query.order_by(ScheduleOccurrences.starts_at)).all()
    return [{
        **as_dict(row[0]),
        "item_id": row.item_id,
        "item_title": row.item_title,
        "type_code": row.type_code,
        "status_code": row.status_code,
    } for row in rows]


def update_occurrence(user_id: int, occurrence_id: int, body: StatusInput, session: Session) -> dict[str, Any]:
    """Update an occurrence's status and completion timestamp."""
    row = require(session, ScheduleOccurrences, occurrence_id, "Occurrence")
    require_accessible_item(session, user_id, row.schedule.item_id, "Occurrence")
    row.status_id = dictionary_id(session, OccurrenceStatuses, body.code)
    row.completed_at = _utc_now_iso() if body.code == "COMPLETED" else None
    return as_dict(row)


def notification_configs(user_id: int, item_id: int, session: Session) -> list[dict[str, Any]]:
    """List notification configurations for an item owned by the user."""
    item = require_accessible_item(session, user_id, item_id)
    return [as_dict(row) for row in item.notification_configs]


def add_notification_config(user_id: int, item_id: int, body: NotificationConfigInput, session: Session) -> dict[str, Any]:
    """Create a notification configuration for an owned item."""
    require_accessible_item(session, user_id, item_id)
    row = NotificationConfigs(item_id=item_id, label=body.label, offset_minutes=body.offset_minutes, is_enabled=body.is_enabled)
    session.add(row)
    session.flush()
    return as_dict(row)


def notifications(user_id: int, status_code: str | None, session: Session) -> list[dict[str, Any]]:
    """List the user's notifications, optionally filtered by status."""
    query = select(Notifications, Items.title.label("item_title"), NotificationStatuses.code.label("status_code")) \
        .join(Notifications.status).join(Notifications.schedule_occurrence).join(ScheduleOccurrences.schedule).join(Schedules.item)
    query = query.where((Items.user_id == user_id) | (Items.is_private.is_(False)))
    if status_code:
        query = query.where(NotificationStatuses.code == status_code)
    rows = session.execute(query.order_by(Notifications.notify_at)).all()
    return [{**as_dict(row[0]), "item_title": row.item_title, "status_code": row.status_code} for row in rows]


def update_notification(user_id: int, notification_id: int, body: StatusInput, session: Session) -> dict[str, Any]:
    """Update a notification's status and delivery details."""
    row = require(session, Notifications, notification_id, "Notification")
    require_accessible_item(session, user_id, row.schedule_occurrence.schedule.item_id, "Notification")
    row.status_id = dictionary_id(session, NotificationStatuses, body.code)
    row.sent_at = _utc_now_iso() if body.code == "SENT" else None
    row.error_message = body.error_message
    return as_dict(row)
