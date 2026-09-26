from datetime import datetime

from sqlalchemy import select

from app import daemon
from app.models import (
    ItemStatuses,
    ItemTypes,
    Items,
    NotificationConfigs,
    Notifications,
    RecurrenceRules,
    RecurrenceTypes,
    ScheduleOccurrences,
    Schedules,
)


def test_occurrence_and_notification_generation_is_idempotent(test_context, monkeypatch) -> None:
    with test_context.session_factory() as session:
        user_id = test_context.user_ids["alice"]
        item = Items(
            user_id=user_id,
            type_id=session.scalar(select(ItemTypes.id).where(ItemTypes.code == "TASK")),
            status_id=session.scalar(select(ItemStatuses.id).where(ItemStatuses.code == "TODO")),
            title="Test daemon",
        )
        session.add(item)
        session.flush()
        schedule = Schedules(item_id=item.id, start_at="2030-05-01T10:00:00", end_at="11:00")
        session.add(schedule)
        session.add(NotificationConfigs(item_id=item.id, offset_minutes=30, is_enabled=True))
        session.flush()

        now = datetime(2030, 5, 1, 0, 0)
        assert daemon.create_occurrences(session, now) == 1
        assert daemon.create_occurrences(session, now) == 0
        assert daemon.create_notifications(session) == 1
        assert daemon.create_notifications(session) == 0
        session.commit()

        notification = session.scalar(select(Notifications))
        assert notification.notify_at == "2030-05-01T09:30:00"

        sent = []
        monkeypatch.setattr(daemon, "send_notification", sent.append)
        assert daemon.send_due_notifications(session, datetime(2030, 5, 1, 9, 29)) == 0
        assert daemon.send_due_notifications(session, datetime(2030, 5, 1, 9, 30)) == 1
        assert sent == [notification]


def test_monthly_occurrences_clamp_to_last_day(test_context) -> None:
    with test_context.session_factory() as session:
        recurrence_type = session.scalar(select(RecurrenceTypes).where(RecurrenceTypes.code == "MONTHLY"))
        rule = RecurrenceRules(
            recurrence_type_id=recurrence_type.id,
            label="Mensuel le 31",
            expression="monthly",
            day_of_month=31,
        )
        item = Items(
            user_id=test_context.user_ids["alice"],
            type_id=session.scalar(select(ItemTypes.id).where(ItemTypes.code == "TASK")),
            status_id=session.scalar(select(ItemStatuses.id).where(ItemStatuses.code == "TODO")),
            title="Mensuel",
        )
        session.add_all([rule, item])
        session.flush()
        schedule = Schedules(item_id=item.id, start_at="2031-01-31T09:00:00", recurrence_rule=rule)
        session.add(schedule)
        session.flush()

        assert daemon.create_occurrences(session, datetime(2031, 3, 31, 23, 59)) > 0
        starts = session.scalars(
            select(ScheduleOccurrences.starts_at)
            .where(ScheduleOccurrences.schedule_id == schedule.id)
            .order_by(ScheduleOccurrences.starts_at)
        ).all()

    assert starts[:3] == [
        "2031-01-31T09:00:00",
        "2031-02-28T09:00:00",
        "2031-03-31T09:00:00",
    ]


def test_inactive_schedules_do_not_generate_occurrences(test_context) -> None:
    with test_context.session_factory() as session:
        item = Items(
            user_id=test_context.user_ids["alice"],
            type_id=session.scalar(select(ItemTypes.id).where(ItemTypes.code == "NOTE")),
            status_id=session.scalar(select(ItemStatuses.id).where(ItemStatuses.code == "TODO")),
            title="Inactif",
        )
        session.add(item)
        session.flush()
        session.add(Schedules(item_id=item.id, start_at="2030-01-01T10:00:00", is_active=False))
        session.flush()

        assert daemon.create_occurrences(session, datetime(2030, 1, 1)) == 0
        assert session.scalar(select(ScheduleOccurrences.id)) is None
