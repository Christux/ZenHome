"""Background tasks for occurrences and notifications."""

from __future__ import annotations

import asyncio
import calendar
from collections.abc import Callable, Iterable
from datetime import date, datetime, time, timedelta
import logging
import re
import unicodedata

from python_ntfy import MessageSendError, NtfyClient, ViewAction
from sqlalchemy import select
from sqlalchemy.orm import Session

from .database import SessionLocal
from .globals import (
    HOME_URL,
    NTFY_PASSWORD,
    NTFY_SERVER,
    NTFY_TOKEN,
    NTFY_TOPIC_PREFIX,
    NTFY_USER,
    NOTIFICATIONS_INTERVAL_SECONDS,
    OCCURRENCES_INTERVAL_SECONDS,
    OCCURRENCES_HORIZON_DAYS,
)
from .models import (
    NotificationConfigs,
    NotificationStatuses,
    Notifications,
    OccurrenceStatuses,
    RecurrenceRules,
    ScheduleOccurrences,
    Schedules,
)

logger = logging.getLogger(__name__)


def send_notification(notification: Notifications) -> None:
    """Sends a notification to the item's public or private ntfy topic."""
    item = notification.schedule_occurrence.schedule.item
    if item.is_private:
        channel = _topic_component(item.user.display_name) or f"user-{item.user_id}"
    else:
        channel = "general"
    topic_prefix = _topic_component(NTFY_TOPIC_PREFIX) or "zenhome"
    topic = f"{topic_prefix}_{channel}"

    if NTFY_TOKEN:
        auth = NTFY_TOKEN
    elif bool(NTFY_USER) != bool(NTFY_PASSWORD):
        raise ValueError("NTFY_USER et NTFY_PASSWORD doivent être configurés ensemble.")
    elif NTFY_USER and NTFY_PASSWORD:
        auth = (NTFY_USER, NTFY_PASSWORD)
    else:
        auth = None
    client = NtfyClient(topic=topic, server=NTFY_SERVER, auth=auth)
    starts_at = _parse_datetime(notification.schedule_occurrence.starts_at)
    message = f"Prévu le {starts_at.strftime('%d/%m/%Y à %H:%M')}"
    if item.content:
        message = f"{item.content}\n\n{message}"
    client.send(
        message=message,
        title=notification.notification_config.label or item.title,
        actions=[ViewAction(label="Voir l'item", url=f"{HOME_URL.rstrip('/')}/item/{item.id}")],
    )


def _topic_component(value: str) -> str:
    """Normalizes a name into a lowercase ntfy topic component."""
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii").lower()
    return re.sub(r"[^a-z0-9_-]+", "_", normalized).strip("_-")


def _parse_datetime(value: str) -> datetime:
    """Converts an ISO 8601 string into a naive datetime object."""
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone().replace(tzinfo=None)
    return parsed


def _add_months(value: date, months: int) -> date:
    """Adds a whole number of months to a date while preserving the last valid calendar day."""
    month_index = value.year * 12 + value.month - 1 + months
    year, month_index = divmod(month_index, 12)
    month = month_index + 1
    return date(year, month, min(value.day, calendar.monthrange(year, month)[1]))


def _occurrence_starts(schedule: Schedules, horizon: datetime) -> Iterable[datetime]:
    """Generates the start timestamps for an occurrence from a given schedule."""
    first = _parse_datetime(schedule.start_at)
    if schedule.recurrence_rule is None:
        if first <= horizon:
            yield first
        return

    rule: RecurrenceRules = schedule.recurrence_rule
    recurrence_type = rule.recurrence_type.code
    weekdays = {weekday.weekday for weekday in rule.recurrence_rule_weekdays}
    first_date = first.date()
    last_date = horizon.date()

    if recurrence_type == "WEEKLY":
        current = first_date
        selected_weekdays = weekdays or {first.isoweekday()}
        while current <= last_date:
            if current >= first_date and current.isoweekday() in selected_weekdays:
                yield datetime.combine(current, first.timetz())
            current += timedelta(days=1)
        return

    if recurrence_type == "DAILY":
        current = first
        while current <= horizon:
            yield current
            current += timedelta(days=1)
        return

    step_by_type = {"MONTHLY": 1, "QUARTERLY": 3, "HALF_YEAR": 6, "YEARLY": 12}
    if recurrence_type in step_by_type:
        month_offset = 0
        while True:
            occurrence_date = _add_months(first_date, month_offset * step_by_type[recurrence_type])
            if recurrence_type == "YEARLY" and rule.month_of_year:
                occurrence_date = date(occurrence_date.year, rule.month_of_year, min(
                    rule.day_of_month or first_date.day,
                    calendar.monthrange(occurrence_date.year, rule.month_of_year)[1],
                ))
            elif rule.day_of_month:
                occurrence_date = occurrence_date.replace(
                    day=min(rule.day_of_month, calendar.monthrange(occurrence_date.year, occurrence_date.month)[1])
                )
            occurrence = datetime.combine(occurrence_date, first.timetz())
            if occurrence > horizon:
                break
            if occurrence >= first:
                yield occurrence
            month_offset += 1
        return

    if first <= horizon:
        yield first


def _end_at(schedule: Schedules, starts_at: datetime) -> str | None:
    """Calculates the ISO end date for an occurrence from a schedule."""
    if not schedule.end_at:
        return None
    try:
        end_value = _parse_datetime(schedule.end_at)
        return datetime.combine(starts_at.date(), end_value.timetz()).isoformat()
    except ValueError:
        try:
            end_value = time.fromisoformat(schedule.end_at)
            return datetime.combine(starts_at.date(), end_value).isoformat()
        except ValueError:
            logger.warning("Invalid end time for schedule %s", schedule.id)
            return None


def create_occurrences(session: Session, now: datetime | None = None) -> int:
    """Creates missing occurrences up to the horizon calculated from ``now``."""
    now = now or datetime.now()
    if now.tzinfo is not None:
        now = now.astimezone().replace(tzinfo=None)
    horizon = now + timedelta(days=OCCURRENCES_HORIZON_DAYS)
    pending_status_id = session.scalar(select(OccurrenceStatuses.id).where(OccurrenceStatuses.code == "PENDING"))
    if pending_status_id is None:
        logger.warning("Occurrence status PENDING is missing")
        return 0

    created = 0
    schedules = session.scalars(select(Schedules).where(Schedules.is_active.is_(True))).all()
    for schedule in schedules:
        existing = set(session.scalars(
            select(ScheduleOccurrences.starts_at).where(ScheduleOccurrences.schedule_id == schedule.id)
        ))
        for starts_at in _occurrence_starts(schedule, horizon):
            starts_at_value = starts_at.isoformat()
            if starts_at_value in existing:
                continue
            session.add(ScheduleOccurrences(
                schedule_id=schedule.id,
                status_id=pending_status_id,
                starts_at=starts_at_value,
                ends_at=_end_at(schedule, starts_at),
            ))
            existing.add(starts_at_value)
            created += 1
    session.flush()
    return created


def create_notifications(session: Session) -> int:
    """Creates notifications planned for existing occurrences."""
    pending_status_id = session.scalar(select(NotificationStatuses.id).where(NotificationStatuses.code == "PENDING"))
    if pending_status_id is None:
        logger.warning("Notification status PENDING is missing")
        return 0

    created = 0
    occurrences = session.scalars(select(ScheduleOccurrences)).all()
    for occurrence in occurrences:
        if occurrence.schedule is None:
            logger.warning(
                "Occurrence %s skipped: schedule %s not found",
                occurrence.id,
                occurrence.schedule_id,
            )
            continue
        configs = session.scalars(
            select(NotificationConfigs).where(
                NotificationConfigs.item_id == occurrence.schedule.item_id,
                NotificationConfigs.is_enabled.is_(True),
            )
        ).all()
        for config in configs:
            exists = session.scalar(select(Notifications.id).where(
                Notifications.schedule_occurrence_id == occurrence.id,
                Notifications.notification_config_id == config.id,
            ))
            if exists is not None:
                continue
            notify_at = _parse_datetime(occurrence.starts_at) - timedelta(minutes=config.offset_minutes)
            session.add(Notifications(
                schedule_occurrence_id=occurrence.id,
                notification_config_id=config.id,
                status_id=pending_status_id,
                notify_at=notify_at.isoformat(),
            ))
            created += 1
    session.flush()
    return created


def send_due_notifications(session: Session, now: datetime | None = None) -> int:
    """Calls ``send_notification`` for every notification that has reached its due time."""
    now = now or datetime.now()
    if now.tzinfo is not None:
        now = now.astimezone().replace(tzinfo=None)
    statuses = dict(session.execute(select(
        NotificationStatuses.code,
        NotificationStatuses.id,
    ).where(NotificationStatuses.code.in_(("PENDING", "SENT", "FAILED")))).all())
    pending_status_id = statuses.get("PENDING")
    if pending_status_id is None or statuses.get("SENT") is None or statuses.get("FAILED") is None:
        logger.warning("Notification statuses PENDING, SENT, or FAILED are missing")
        return 0
    due = session.scalars(select(Notifications).where(
        Notifications.status_id == pending_status_id,
        Notifications.notify_at <= now.isoformat(),
    )).all()
    for notification in due:
        try:
            send_notification(notification)
        except MessageSendError as exc:
            notification.status_id = statuses["FAILED"]
            notification.error_message = str(exc)
            logger.exception("ntfy failed to send notification %s", notification.id)
        except Exception as exc:
            notification.status_id = statuses["FAILED"]
            notification.error_message = str(exc)
            logger.exception("Failed to send notification %s", notification.id)
        else:
            notification.status_id = statuses["SENT"]
            notification.sent_at = datetime.now().isoformat()
            notification.error_message = None
    return len(due)


def run_occurrences_once() -> None:
    """Creates missing occurrences in its own session."""
    session = SessionLocal()
    try:
        occurrences = create_occurrences(session)
        session.commit()
        if occurrences:
            logger.info("Daemon: %s occurrences created", occurrences)
    except Exception:
        session.rollback()
        logger.exception("Error creating occurrences")
    finally:
        session.close()


def run_notifications_once() -> None:
    """Creates and sends due notifications in its own session."""
    session = SessionLocal()
    try:
        notifications = create_notifications(session)
        due = send_due_notifications(session)
        session.commit()
        if notifications or due:
            logger.info("Daemon: %s notifications created, %s pending delivery", notifications, due)
    except Exception:
        session.rollback()
        logger.exception("Error processing notifications")
    finally:
        session.close()


async def _periodic_loop(
    task: Callable[[], None],
    interval_seconds: int,
    stop_event: asyncio.Event,
) -> None:
    """Runs a synchronous daemon task periodically until shutdown."""
    while not stop_event.is_set():
        await asyncio.to_thread(task)
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval_seconds)
        except asyncio.TimeoutError:
            continue


async def daemon_loop(stop_event: asyncio.Event) -> None:
    """Runs occurrence generation daily and notification processing each minute."""
    await asyncio.gather(
        _periodic_loop(run_occurrences_once, OCCURRENCES_INTERVAL_SECONDS, stop_event),
        _periodic_loop(run_notifications_once, NOTIFICATIONS_INTERVAL_SECONDS, stop_event),
    )
