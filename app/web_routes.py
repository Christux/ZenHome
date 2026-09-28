"""HTTP routes for the ZenHome web interface and API."""

from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from . import services
from .auth import get_current_user
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
from .models import Users

router = APIRouter(prefix="/api", tags=["interface web"], dependencies=[Depends(get_current_user)])
public_router = APIRouter(tags=["interface web"])


@public_router.get("/", include_in_schema=False)
def home() -> FileResponse:
    """Serve the application shell at the root URL."""
    return FileResponse(PROJECT_DIR / "index.html")


@public_router.get("/item/{item_id}", include_in_schema=False)
def item_page(item_id: int) -> FileResponse:
    """Serve the application shell for a permanent item URL."""
    if item_id < 1:
        raise HTTPException(status_code=404, detail="Item not found.")
    return FileResponse(PROJECT_DIR / "index.html")


@public_router.get("/{page}", include_in_schema=False)
def web_page(page: str) -> FileResponse:
    """Serve the application shell for a supported SPA page."""
    if page not in {"notes", "checklists", "tasks", "kanban", "calendar"}:
        raise HTTPException(status_code=404, detail="Page not found.")
    return FileResponse(PROJECT_DIR / "index.html")


@public_router.get("/api/health")
def health() -> dict[str, str]:
    """Return the service health status."""
    return {"status": "ok"}


@router.get("/auth/me")
def authenticated_user(user: Users = Depends(get_current_user)) -> dict[str, Any]:
    """Return the authenticated user's public profile."""
    return {"id": user.id, "display_name": user.display_name}


if ZENHOME_ENV == "development":
    @public_router.get("/api/dev/version")
    def development_version() -> dict[str, str]:
        """Return a signature that changes when development files change."""
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


@router.get("/items")
def list_items(
    item_type: Literal["NOTE", "CHECKLIST", "TASK"] | None = Query(default=None),
    include_archived: bool = Query(default=False),
    user: Users = Depends(get_current_user),
    db: Session = Depends(get_session),
) -> list[dict[str, Any]]:
    """Return the authenticated user's items with the requested filters."""
    return services.list_items(user.id, db, item_type, include_archived)


@router.post("/items", status_code=status.HTTP_201_CREATED)
def create_item(
    payload: ItemCreate,
    user: Users = Depends(get_current_user),
    db: Session = Depends(get_session),
) -> dict[str, Any]:
    """Create an item for the authenticated user."""
    return services.create_item(user.id, payload, db)


@router.patch("/items/{item_id}")
def update_item(
    item_id: int,
    payload: ItemUpdate,
    user: Users = Depends(get_current_user),
    db: Session = Depends(get_session),
) -> dict[str, Any]:
    """Update editable fields on an item."""
    return services.update_item(user.id, item_id, payload, db)


@router.delete("/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_item(item_id: int, user: Users = Depends(get_current_user), db: Session = Depends(get_session)) -> None:
    """Delete an item and its dependent data."""
    services.delete_item(user.id, item_id, db)


@router.patch("/items/{item_id}/status")
def update_item_status(
    item_id: int,
    payload: ItemStatusUpdate,
    user: Users = Depends(get_current_user),
    db: Session = Depends(get_session),
) -> dict[str, Any]:
    """Update the status of an item."""
    return services.update_item_status(user.id, item_id, payload, db)


@router.get("/dashboard")
def dashboard(user: Users = Depends(get_current_user), db: Session = Depends(get_session)) -> dict[str, Any]:
    """Return dashboard counts and upcoming occurrences."""
    return services.dashboard(user.id, db)


@router.get("/dictionaries/{name}")
def dictionaries(name: str, db: Session = Depends(get_session)) -> list[dict[str, Any]]:
    """Return active entries from a business dictionary."""
    return services.dictionaries(name, db)


@router.get("/items/{item_id}/detail")
def item_detail(item_id: int, user: Users = Depends(get_current_user), db: Session = Depends(get_session)) -> dict[str, Any]:
    """Return an item with its related checklist and schedule data."""
    return services.item_detail(user.id, item_id, db)


@router.post("/items/{item_id}/checklist-items", status_code=status.HTTP_201_CREATED)
def add_checklist_item(
    item_id: int,
    body: ChecklistInput,
    user: Users = Depends(get_current_user),
    db: Session = Depends(get_session),
) -> dict[str, Any]:
    """Add a checklist row to an item."""
    return services.add_checklist_item(user.id, item_id, body, db)


@router.post("/items/{item_id}/checklist-items/reset")
def reset_checklist(item_id: int, user: Users = Depends(get_current_user), db: Session = Depends(get_session)) -> dict[str, int]:
    """Reset all checked rows in a checklist."""
    return services.reset_checklist(user.id, item_id, db)


@router.patch("/checklist-items/{checklist_item_id}")
def edit_checklist_item(
    checklist_item_id: int,
    body: ChecklistInput,
    user: Users = Depends(get_current_user),
    db: Session = Depends(get_session),
) -> dict[str, Any]:
    """Edit a checklist row."""
    return services.edit_checklist_item(user.id, checklist_item_id, body, db)


@router.delete("/checklist-items/{checklist_item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_checklist_item(
    checklist_item_id: int,
    user: Users = Depends(get_current_user),
    db: Session = Depends(get_session),
) -> None:
    """Delete a checklist row."""
    services.delete_checklist_item(user.id, checklist_item_id, db)


@router.get("/recurrence-rules")
def recurrence_rules(db: Session = Depends(get_session)) -> list[dict[str, Any]]:
    """Return available recurrence rules."""
    return services.recurrence_rules(db)


@router.post("/recurrence-rules", status_code=status.HTTP_201_CREATED)
def add_rule(body: RuleInput, db: Session = Depends(get_session)) -> dict[str, int]:
    """Create a recurrence rule."""
    return services.add_rule(body, db)


@router.delete("/recurrence-rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_rule(rule_id: int, db: Session = Depends(get_session)) -> None:
    """Delete a recurrence rule."""
    services.delete_rule(rule_id, db)


@router.get("/items/{item_id}/schedules")
def schedules(item_id: int, user: Users = Depends(get_current_user), db: Session = Depends(get_session)) -> list[dict[str, Any]]:
    """List schedules attached to an item."""
    return services.schedules(user.id, item_id, db)


@router.post("/items/{item_id}/schedules", status_code=status.HTTP_201_CREATED)
def add_schedule(
    item_id: int,
    body: ScheduleInput,
    user: Users = Depends(get_current_user),
    db: Session = Depends(get_session),
) -> dict[str, Any]:
    """Add a schedule to an item."""
    return services.add_schedule(user.id, item_id, body, db)


@router.delete("/schedules/{schedule_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_schedule(schedule_id: int, user: Users = Depends(get_current_user), db: Session = Depends(get_session)) -> None:
    """Delete a schedule."""
    services.delete_schedule(user.id, schedule_id, db)


@router.get("/occurrences")
def occurrences(
    start_at: str | None = None,
    end_at: str | None = None,
    user: Users = Depends(get_current_user),
    db: Session = Depends(get_session),
) -> list[dict[str, Any]]:
    """List the user's occurrences within an optional time range."""
    return services.occurrences(user.id, start_at, end_at, db)


@router.patch("/occurrences/{occurrence_id}/status")
def update_occurrence(
    occurrence_id: int,
    body: StatusInput,
    user: Users = Depends(get_current_user),
    db: Session = Depends(get_session),
) -> dict[str, Any]:
    """Update the status of a scheduled occurrence."""
    return services.update_occurrence(user.id, occurrence_id, body, db)


@router.get("/items/{item_id}/notification-configs")
def notification_configs(
    item_id: int,
    user: Users = Depends(get_current_user),
    db: Session = Depends(get_session),
) -> list[dict[str, Any]]:
    """List notification configurations for an item."""
    return services.notification_configs(user.id, item_id, db)


@router.post("/items/{item_id}/notification-configs", status_code=status.HTTP_201_CREATED)
def add_notification_config(
    item_id: int,
    body: NotificationConfigInput,
    user: Users = Depends(get_current_user),
    db: Session = Depends(get_session),
) -> dict[str, Any]:
    """Create a notification configuration for an item."""
    return services.add_notification_config(user.id, item_id, body, db)


@router.get("/notifications")
def notifications(
    status_code: str | None = Query(default=None),
    user: Users = Depends(get_current_user),
    db: Session = Depends(get_session),
) -> list[dict[str, Any]]:
    """List notifications, optionally filtered by status."""
    return services.notifications(user.id, status_code, db)


@router.patch("/notifications/{notification_id}/status")
def update_notification(
    notification_id: int,
    body: StatusInput,
    user: Users = Depends(get_current_user),
    db: Session = Depends(get_session),
) -> dict[str, Any]:
    """Update a notification's status and delivery details."""
    return services.update_notification(user.id, notification_id, body, db)
