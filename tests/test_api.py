from datetime import datetime, timedelta

from sqlalchemy import select

from app.models import Items


def auth(token: str = "alice-test-token") -> dict[str, str]:
    return {"X-Auth-Token": token}


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
        "/api/items", headers=auth("bob-test-token"), json={"title": "Privé", "type_code": "TASK"}
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

    occurrence = client.get("/api/occurrences", headers=auth()).json()[0]
    assert occurrence["item_title"] == "Rendez-vous"
    assert occurrence["ends_at"] == f"{schedule_start.date().isoformat()}T21:00:00"

    from app.daemon import create_notifications, create_occurrences

    with test_context.session_factory() as session:
        assert create_occurrences(session, schedule_start.replace(hour=0)) == 0
        assert create_notifications(session) == 1
        session.commit()

    occurrence = client.get("/api/occurrences", headers=auth()).json()[0]
    completed = client.patch(
        f"/api/occurrences/{occurrence['id']}/status", headers=auth(), json={"code": "COMPLETED"}
    ).json()
    assert completed["completed_at"].endswith("+00:00")

    notification = client.get("/api/notifications?status_code=PENDING", headers=auth()).json()[0]
    assert notification["item_title"] == "Rendez-vous"
    assert notification["notify_at"] == f"{schedule_start.date().isoformat()}T19:45:00"
    sent = client.patch(
        f"/api/notifications/{notification['id']}/status", headers=auth(),
        json={"code": "SENT"},
    ).json()
    assert sent["sent_at"].endswith("+00:00")
    assert client.delete(f"/api/schedules/{schedule.json()['id']}", headers=auth()).status_code == 204


def test_dashboard_counts_only_current_users_items(client) -> None:
    for payload in (
        {"title": "Ouverte", "type_code": "TASK"},
        {"title": "Terminée", "type_code": "TASK", "status_code": "DONE"},
        {"title": "Liste", "type_code": "CHECKLIST"},
    ):
        assert client.post("/api/items", headers=auth(), json=payload).status_code == 201
    client.post("/api/items", headers=auth("bob-test-token"), json={
        "title": "Tâche Bob", "type_code": "TASK",
    })

    counts = client.get("/api/dashboard", headers=auth()).json()["counts"]
    assert counts["tasks_total"] == 2
    assert counts["tasks_done"] == 1
    assert counts["checklists_open"] == 1
    assert counts["today"] == 0


def test_dictionary_endpoints(client) -> None:
    types = client.get("/api/dictionaries/item-types", headers=auth())
    assert types.status_code == 200
    assert {row["code"] for row in types.json()} == {"NOTE", "CHECKLIST", "TASK"}
    assert client.get("/api/dictionaries/unknown", headers=auth()).status_code == 404