import asyncio
from datetime import datetime

from sqlalchemy import select

from app import daemon
from app.models import (
    ItemStatuses,
    ItemTypes,
    Items,
    NotificationConfigs,
    NotificationStatuses,
    Notifications,
    RecurrenceRules,
    RecurrenceTypes,
    ScheduleOccurrences,
    Schedules,
)


def test_occurrence_and_notification_generation_is_idempotent(test_context, monkeypatch, caplog) -> None:
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
        assert notification.status.code == "SENT"
        assert notification.sent_at is not None
        session.commit()
        assert daemon.send_due_notifications(session, datetime(2030, 5, 1, 9, 30)) == 0

        notification.status_id = session.scalar(
            select(NotificationStatuses.id).where(NotificationStatuses.code == "PENDING")
        )
        notification.sent_at = None
        session.commit()

        def fail_delivery(_notification):
            raise daemon.MessageSendError("Serveur ntfy indisponible")

        monkeypatch.setattr(daemon, "send_notification", fail_delivery)
        assert daemon.send_due_notifications(session, datetime(2030, 5, 1, 9, 30)) == 1
        assert notification.status_id == session.scalar(
            select(NotificationStatuses.id).where(NotificationStatuses.code == "FAILED")
        )
        assert notification.error_message == "Serveur ntfy indisponible"
        session.commit()
        assert daemon.send_due_notifications(session, datetime(2030, 5, 1, 9, 30)) == 0

        notification.status_id = session.scalar(
            select(NotificationStatuses.id).where(NotificationStatuses.code == "PENDING")
        )
        session.commit()

        def fail_unexpectedly(_notification):
            raise RuntimeError("Erreur inattendue du client ntfy")

        monkeypatch.setattr(daemon, "send_notification", fail_unexpectedly)
        assert daemon.send_due_notifications(session, datetime(2030, 5, 1, 9, 30)) == 1
        assert notification.status_id == session.scalar(
            select(NotificationStatuses.id).where(NotificationStatuses.code == "FAILED")
        )
        assert notification.error_message == "Erreur inattendue du client ntfy"
        assert "Failed to send notification" in caplog.text


def test_daemon_loop_schedules_occurrences_daily_and_notifications_separately(monkeypatch) -> None:
    scheduled = []

    async def capture_schedule(task, interval_seconds, stop_event):
        scheduled.append((task, interval_seconds))
        if len(scheduled) == 2:
            stop_event.set()

    monkeypatch.setattr(daemon, "_periodic_loop", capture_schedule)

    asyncio.run(daemon.daemon_loop(asyncio.Event()))

    assert scheduled == [
        (daemon.run_occurrences_once, daemon.OCCURRENCES_INTERVAL_SECONDS),
        (daemon.run_notifications_once, daemon.NOTIFICATIONS_INTERVAL_SECONDS),
    ]


def test_send_notification_uses_public_and_private_topics(test_context, monkeypatch) -> None:
    clients = []

    class FakeNtfyClient:
        def __init__(self, topic, server, auth):
            self.topic = topic
            clients.append((topic, server, auth))

        def send(self, message, title, actions):
            clients[-1] += (message, title, actions)

    monkeypatch.setattr(daemon, "NtfyClient", FakeNtfyClient)
    monkeypatch.setattr(daemon, "NTFY_TOPIC_PREFIX", "ZenHome")
    monkeypatch.setattr(daemon, "NTFY_SERVER", "https://ntfy.example")
    monkeypatch.setattr(daemon, "HOME_URL", "https://zenhome.example/")
    monkeypatch.setattr(daemon, "NTFY_TOKEN", None)
    monkeypatch.setattr(daemon, "NTFY_USER", None)
    monkeypatch.setattr(daemon, "NTFY_PASSWORD", None)

    with test_context.session_factory() as session:
        alice_id = test_context.user_ids["alice"]
        item_values = (("Public", False), ("Privé", True))
        for title, is_private in item_values:
            item = Items(
                user_id=alice_id,
                type_id=session.scalar(select(ItemTypes.id).where(ItemTypes.code == "TASK")),
                status_id=session.scalar(select(ItemStatuses.id).where(ItemStatuses.code == "TODO")),
                title=title,
                is_private=is_private,
            )
            session.add(item)
            session.flush()
            schedule = Schedules(item_id=item.id, start_at="2030-05-01T10:00:00")
            session.add(schedule)
            session.flush()
            occurrence = ScheduleOccurrences(
                schedule_id=schedule.id,
                status_id=1,
                starts_at="2030-05-01T10:00:00",
            )
            config = NotificationConfigs(item_id=item.id)
            session.add_all((occurrence, config))
            session.flush()
            notification = Notifications(
                schedule_occurrence_id=occurrence.id,
                notification_config_id=config.id,
                status_id=session.scalar(
                    select(NotificationStatuses.id).where(NotificationStatuses.code == "PENDING")
                ),
                notify_at="2030-05-01T09:30:00",
            )
            session.add(notification)
            session.flush()
            daemon.send_notification(notification)

    assert [client[:5] for client in clients] == [
        ("zenhome_general", "https://ntfy.example", None, "Prévu le 2030-05-01T10:00:00", "Public"),
        ("zenhome_alice", "https://ntfy.example", None, "Prévu le 2030-05-01T10:00:00", "Privé"),
    ]
    assert [client[5][0].url for client in clients] == [
        "https://zenhome.example/item/1",
        "https://zenhome.example/item/2",
    ]
    assert all(client[5][0].label == "Voir l'item" for client in clients)


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
