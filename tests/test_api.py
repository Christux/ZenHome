import asyncio
from datetime import datetime, timedelta

import app.main as app_main
from sqlalchemy import select

from app.models import Items


def auth(token: str = "alice-test-token") -> dict[str, str]:
    return {"X-Auth-Token": token}


def test_lifespan_disposes_database_when_daemon_fails(monkeypatch) -> None:
    async def failing_daemon(stop_event: asyncio.Event) -> None:
        await stop_event.wait()
        raise RuntimeError("daemon failure")

    monkeypatch.setattr(app_main, "configure_logging", lambda: None)
    monkeypatch.setattr(app_main, "initialize_database", lambda: None)
    monkeypatch.setattr(app_main, "daemon_loop", failing_daemon)
    disposed = []
    monkeypatch.setattr(app_main.engine, "dispose", lambda: disposed.append(True))

    async def run_lifespan() -> None:
        async with app_main.lifespan(app_main.app):
            pass

    asyncio.run(run_lifespan())

    assert disposed == [True]


def test_health_and_authentication(client) -> None:
    assert client.get("/api/health").json() == {"status": "ok"}
    assert client.get("/api/items").status_code == 401
    assert client.get("/api/items", headers=auth("unknown")).status_code == 401
    assert client.get("/api/auth/me", headers=auth()).json()["display_name"] == "Alice"


def test_item_crud_filters_and_user_isolation(client, test_context) -> None:
    alice_item = client.post(
        "/api/items", headers=auth(), json={"title": "  Mon idée  ", "content": "Texte"}
    )
    bob_item = client.post(
        "/api/items", headers=auth("bob-test-token"), json={
            "title": "Privé", "type_code": "TASK", "is_private": True,
        }
    )
    assert alice_item.status_code == bob_item.status_code == 201
    assert alice_item.json()["title"] == "Mon idée"
    assert [row["title"] for row in client.get("/api/items", headers=auth()).json()] == ["Mon idée"]
    assert client.get(f"/api/items/{bob_item.json()['id']}/detail", headers=auth()).status_code == 404
    assert client.patch(
        f"/api/items/{bob_item.json()['id']}", headers=auth(), json={"title": "Volé"}
    ).status_code == 404

    updated = client.patch(
        f"/api/items/{alice_item.json()['id']}", headers=auth(), json={"content": "Modifié"}
    )
    assert updated.json()["content"] == "Modifié"
    assert updated.json()["updated_at"].endswith("+00:00")
    status = client.patch(
        f"/api/items/{alice_item.json()['id']}/status", headers=auth(), json={"status_code": "DONE"}
    )
    assert status.json()["status_code"] == "DONE"
    assert client.get("/api/items?item_type=TASK", headers=auth()).json() == []

    with test_context.session_factory() as session:
        item = session.scalar(select(Items).where(Items.id == alice_item.json()["id"]))
        item.is_archived = True
        session.commit()
    assert client.get("/api/items", headers=auth()).json() == []
    assert len(client.get("/api/items?include_archived=true", headers=auth()).json()) == 1

    assert client.delete(f"/api/items/{alice_item.json()['id']}", headers=auth()).status_code == 204
    assert client.get(f"/api/items/{alice_item.json()['id']}/detail", headers=auth()).status_code == 404


def test_shared_and_private_items_access(client) -> None:
    shared = client.post("/api/items", headers=auth(), json={"title": "Partagé"}).json()
    shared_checklist = client.post("/api/items", headers=auth(), json={
        "title": "Checklist partagée", "type_code": "CHECKLIST",
        "checklist_items": [{"label": "Case cochée", "is_checked": True}],
    }).json()
    private = client.post("/api/items", headers=auth(), json={
        "title": "Privé", "type_code": "CHECKLIST", "is_private": True,
        "checklist_items": [{"label": "Ligne"}],
    }).json()
    bob_headers = auth("bob-test-token")

    bob_items = client.get("/api/items", headers=bob_headers).json()
    assert {item["title"] for item in bob_items} == {"Partagé", "Checklist partagée"}
    assert client.get(f"/api/items/{shared['id']}/detail", headers=bob_headers).status_code == 200
    assert client.patch(f"/api/items/{shared['id']}", headers=bob_headers, json={
        "title": "Modifié par Bob",
    }).json()["title"] == "Modifié par Bob"
    assert client.post(
        f"/api/items/{shared_checklist['id']}/checklist-items/reset", headers=bob_headers,
    ).json()["reset_count"] == 1
    edited_checklist = client.patch(
        f"/api/items/{shared_checklist['id']}", headers=bob_headers,
        json={"title": "Checklist partagée modifiée"},
    )
    assert edited_checklist.status_code == 200
    assert edited_checklist.json()["id"] == shared_checklist["id"]
    added_check = client.post(
        f"/api/items/{shared_checklist['id']}/checklist-items", headers=bob_headers,
        json={"label": "Ajout de Bob"},
    )
    assert added_check.status_code == 201
    assert len([
        item for item in client.get("/api/items?item_type=CHECKLIST", headers=bob_headers).json()
        if item["id"] == shared_checklist["id"]
    ]) == 1
    assert len(client.get(
        f"/api/items/{shared_checklist['id']}/detail", headers=auth(),
    ).json()["checklist_items"]) == 2
    assert client.get(f"/api/items/{private['id']}/detail", headers=bob_headers).status_code == 404
    assert client.patch(f"/api/items/{private['id']}", headers=bob_headers, json={
        "title": "Accès interdit",
    }).status_code == 404
    assert client.patch(f"/api/items/{shared['id']}", headers=bob_headers, json={
        "is_private": True,
    }).status_code == 403

    assert client.patch(f"/api/items/{shared['id']}", headers=auth(), json={
        "is_private": True,
    }).json()["is_private"] is True
    assert all(item["id"] != shared["id"] for item in client.get("/api/items", headers=bob_headers).json())


def test_checklist_creation_edit_reset_and_delete(client) -> None:
    created = client.post("/api/items", headers=auth(), json={
        "title": "Courses", "type_code": "CHECKLIST",
        "checklist_items": [{"label": "Pain"}, {"label": "Lait", "position": 3}],
    })
    assert created.status_code == 201
    item_id = created.json()["id"]

    detail = client.get(f"/api/items/{item_id}/detail", headers=auth()).json()
    assert [row["position"] for row in detail["checklist_items"]] == [0, 3]
    added = client.post(
        f"/api/items/{item_id}/checklist-items", headers=auth(), json={"label": "Oeufs"}
    ).json()
    assert added["position"] == 4
    edited = client.patch(
        f"/api/checklist-items/{added['id']}", headers=auth(),
        json={"label": "Oeufs frais", "is_checked": True},
    ).json()
    assert edited["is_checked"] is True
    assert edited["checked_at"].endswith("+00:00")
    assert client.post(f"/api/items/{item_id}/checklist-items/reset", headers=auth()).json() == {
        "item_id": item_id, "reset_count": 1
    }
    assert client.delete(f"/api/checklist-items/{added['id']}", headers=auth()).status_code == 204
    assert client.post("/api/items", headers=auth(), json={
        "title": "Note invalide", "checklist_items": [{"label": "Ligne"}],
    }).status_code == 422


def test_item_notification_configs_create_replace_and_validate(client) -> None:
    created = client.post("/api/items", headers=auth(), json={
        "title": "Rendez-vous",
        "notification_configs": [
            {"offset_minutes": 60},
            {"label": "Juste avant", "offset_minutes": 5},
        ],
    })
    assert created.status_code == 201
    item_id = created.json()["id"]
    configs = client.get(f"/api/items/{item_id}/detail", headers=auth()).json()["notification_configs"]
    assert [config["offset_minutes"] for config in configs] == [60, 5]

    assert client.patch(f"/api/items/{item_id}", headers=auth(), json={
        "notification_configs": [{"offset_minutes": 10}],
    }).status_code == 200
    configs = client.get(f"/api/items/{item_id}/detail", headers=auth()).json()["notification_configs"]
    assert [config["offset_minutes"] for config in configs] == [10]

    assert client.patch(f"/api/items/{item_id}", headers=auth(), json={"title": "Modifié"}).status_code == 200
    configs = client.get(f"/api/items/{item_id}/detail", headers=auth()).json()["notification_configs"]
    assert [config["offset_minutes"] for config in configs] == [10]
    assert client.post("/api/items", headers=auth(), json={
        "title": "Rappel invalide", "notification_configs": [{"offset_minutes": -1}],
    }).status_code == 422


def test_recurrence_rules_are_created_listed_and_validated(client) -> None:
    created = client.post("/api/recurrence-rules", headers=auth(), json={
        "recurrence_type_code": "WEEKLY", "label": "Lundi mercredi",
        "expression": "weekly", "weekdays": [1, 3, 3],
    })
    assert created.status_code == 201
    rules = client.get("/api/recurrence-rules", headers=auth()).json()
    rule = next(rule for rule in rules if rule["id"] == created.json()["id"])
    assert rule["weekdays"] == [1, 3]
    assert rule["recurrence_type_code"] == "WEEKLY"
    assert client.post("/api/recurrence-rules", headers=auth(), json={
        "recurrence_type_code": "WEEKLY", "label": "Invalide",
        "expression": "weekly", "weekdays": [8],
    }).status_code == 422
    assert client.delete(
        f"/api/recurrence-rules/{created.json()['id']}", headers=auth()
    ).status_code == 204


def test_schedule_occurrence_and_notification_lifecycle(client, test_context) -> None:
    schedule_start = (datetime.now() + timedelta(days=1)).replace(
        hour=20, minute=0, second=0, microsecond=0
    )
    item = client.post("/api/items", headers=auth(), json={
        "title": "Rendez-vous", "type_code": "TASK",
    }).json()
    schedule = client.post(f"/api/items/{item['id']}/schedules", headers=auth(), json={
        "start_at": schedule_start.isoformat(), "end_at": "21:00",
    })
    assert schedule.status_code == 201
    config = client.post(f"/api/items/{item['id']}/notification-configs", headers=auth(), json={
        "label": "Rappel", "offset_minutes": 15,
    })
    assert config.status_code == 201
    notification = client.get("/api/notifications?status_code=PENDING", headers=auth()).json()[0]
    assert notification["item_title"] == "Rendez-vous"
    assert notification["notify_at"] == f"{schedule_start.date().isoformat()}T19:45:00"

    occurrence = client.get("/api/occurrences", headers=auth()).json()[0]
    assert occurrence["item_title"] == "Rendez-vous"
    assert occurrence["ends_at"] == f"{schedule_start.date().isoformat()}T21:00:00"

    from app.daemon import create_notifications, create_occurrences

    with test_context.session_factory() as session:
        assert create_occurrences(session, schedule_start.replace(hour=0)) == 0
        assert create_notifications(session) == 0
        session.commit()

    occurrence = client.get("/api/occurrences", headers=auth()).json()[0]
    completed = client.patch(
        f"/api/occurrences/{occurrence['id']}/status", headers=auth(), json={"code": "COMPLETED"}
    ).json()
    assert completed["completed_at"].endswith("+00:00")

    sent = client.patch(
        f"/api/notifications/{notification['id']}/status", headers=auth(),
        json={"code": "SENT"},
    ).json()
    assert sent["sent_at"].endswith("+00:00")
    assert client.delete(f"/api/schedules/{schedule.json()['id']}", headers=auth()).status_code == 204


def test_new_item_schedule_creates_configured_notification(client) -> None:
    schedule_start = (datetime.now() + timedelta(days=1)).replace(
        hour=20, minute=0, second=0, microsecond=0
    )
    item = client.post("/api/items", headers=auth(), json={
        "title": "Nouvel item",
        "type_code": "TASK",
        "notification_configs": [{"offset_minutes": 15}],
    }).json()

    schedule = client.post(f"/api/items/{item['id']}/schedules", headers=auth(), json={
        "start_at": schedule_start.isoformat(),
    })

    assert schedule.status_code == 201
    notifications = client.get("/api/notifications?status_code=PENDING", headers=auth()).json()
    notification = next(row for row in notifications if row["item_title"] == "Nouvel item")
    assert notification["notify_at"] == f"{schedule_start.date().isoformat()}T19:45:00"


def test_dashboard_counts_shared_but_not_private_items(client) -> None:
    for payload in (
        {"title": "Ouverte", "type_code": "TASK"},
        {"title": "Terminée", "type_code": "TASK", "status_code": "DONE"},
        {"title": "Liste", "type_code": "CHECKLIST"},
    ):
        assert client.post("/api/items", headers=auth(), json=payload).status_code == 201
    client.post("/api/items", headers=auth("bob-test-token"), json={
        "title": "Tâche Bob", "type_code": "TASK",
    })
    client.post("/api/items", headers=auth("bob-test-token"), json={
        "title": "Tâche privée Bob", "type_code": "TASK", "is_private": True,
    })

    counts = client.get("/api/dashboard", headers=auth()).json()["counts"]
    assert counts["tasks_total"] == 3
    assert counts["tasks_done"] == 1
    assert counts["checklists_open"] == 1
    assert counts["today"] == 0


def test_dictionary_endpoints(client) -> None:
    types = client.get("/api/dictionaries/item-types", headers=auth())
    assert types.status_code == 200
    assert {row["code"] for row in types.json()} == {"NOTE", "CHECKLIST", "TASK"}
    assert client.get("/api/dictionaries/unknown", headers=auth()).status_code == 404