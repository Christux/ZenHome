"""Tâches de fond pour les occurrences et les notifications."""

from __future__ import annotations

import asyncio
from collections.abc import Iterable
from datetime import date, datetime, time, timedelta
import logging
import calendar

from sqlalchemy import select
from sqlalchemy.orm import Session

from .database import SessionLocal
from .globals import DAEMON_INTERVAL_SECONDS, OCCURRENCES_HORIZON_DAYS
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
    """Envoie une notification. L’implémentation sera ajoutée ultérieurement."""
    _ = notification


def _parse_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone().replace(tzinfo=None)
    return parsed


def _add_months(value: date, months: int) -> date:
    month_index = value.year * 12 + value.month - 1 + months
    year, month_index = divmod(month_index, 12)
    month = month_index + 1
    return date(year, month, min(value.day, calendar.monthrange(year, month)[1]))


def _occurrence_starts(schedule: Schedules, horizon: datetime) -> Iterable[datetime]:
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
            logger.warning("Heure de fin invalide pour la planification %s", schedule.id)
            return None


def create_occurrences(session: Session, now: datetime | None = None) -> int:
    """Crée les occurrences manquantes jusqu’à deux ans après ``now``."""
    now = now or datetime.now()
    if now.tzinfo is not None:
        now = now.astimezone().replace(tzinfo=None)
    horizon = now + timedelta(days=OCCURRENCES_HORIZON_DAYS)
    pending_status_id = session.scalar(select(OccurrenceStatuses.id).where(OccurrenceStatuses.code == "PENDING"))
    if pending_status_id is None:
        logger.warning("Statut d’occurrence PENDING absent")
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
    """Crée les notifications prévues pour les occurrences existantes."""
    pending_status_id = session.scalar(select(NotificationStatuses.id).where(NotificationStatuses.code == "PENDING"))
    if pending_status_id is None:
        logger.warning("Statut de notification PENDING absent")
        return 0

    created = 0
    occurrences = session.scalars(select(ScheduleOccurrences)).all()
    for occurrence in occurrences:
        if occurrence.schedule is None:
            logger.warning(
                "Occurrence %s ignorée : planification %s introuvable",
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
    """Appelle ``send_notification`` pour chaque notification arrivée à échéance."""
    now = now or datetime.now()
    if now.tzinfo is not None:
        now = now.astimezone().replace(tzinfo=None)
    pending_status_id = session.scalar(select(NotificationStatuses.id).where(NotificationStatuses.code == "PENDING"))
    if pending_status_id is None:
        return 0
    due = session.scalars(select(Notifications).where(
        Notifications.status_id == pending_status_id,
        Notifications.notify_at <= now.isoformat(),
    )).all()
    for notification in due:
        send_notification(notification)
    return len(due)


def run_daemon_once() -> None:
    """Exécute un cycle complet dans une session dédiée."""
    session = SessionLocal()
    try:
        occurrences = create_occurrences(session)
        notifications = create_notifications(session)
        due = send_due_notifications(session)
        session.commit()
        if occurrences or notifications or due:
            logger.info("Daemon: %s occurrences, %s notifications créées, %s à envoyer", occurrences, notifications, due)
    except Exception:
        session.rollback()
        logger.exception("Erreur pendant le cycle du daemon")
    finally:
        session.close()


async def daemon_loop(stop_event: asyncio.Event) -> None:
    """Exécute le daemon périodiquement jusqu’à l’arrêt de l’application."""
    while not stop_event.is_set():
        await asyncio.to_thread(run_daemon_once)
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=DAEMON_INTERVAL_SECONDS)
        except asyncio.TimeoutError:
            continue
