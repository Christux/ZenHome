"""Shared fixtures for isolated API and database tests."""

from collections.abc import Generator
from types import SimpleNamespace

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import database
from app.main import app
from app.models import (
    Base,
    ItemStatuses,
    ItemTypes,
    NotificationStatuses,
    OccurrenceStatuses,
    RecurrenceTypes,
    Users,
)


@pytest.fixture
def test_context() -> Generator[SimpleNamespace, None, None]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        use_insertmanyvalues=False,
    )

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection: object, _record: object) -> None:
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with session_factory() as session:
        users = {
            "alice": Users(token="alice-test-token", display_name="Alice"),
            "bob": Users(token="bob-test-token", display_name="Bob"),
        }
        session.add_all(users.values())
        for model, rows in (
            (ItemTypes, (("NOTE", "Note"), ("CHECKLIST", "Checklist"), ("TASK", "Tâche"))),
            (ItemStatuses, (("TODO", "À faire"), ("IN_PROGRESS", "En cours"), ("DONE", "Terminée"), ("CANCELLED", "Annulée"))),
            (NotificationStatuses, (("PENDING", "En attente"), ("SENT", "Envoyée"), ("FAILED", "Échec"), ("CANCELLED", "Annulée"))),
            (OccurrenceStatuses, (("PENDING", "À venir"), ("COMPLETED", "Terminée"), ("SKIPPED", "Ignorée"), ("CANCELLED", "Annulée"))),
            (RecurrenceTypes, (("NONE", "Aucune"), ("DAILY", "Quotidien"), ("WEEKLY", "Hebdomadaire"), ("MONTHLY", "Mensuel"), ("QUARTERLY", "Trimestriel"), ("HALF_YEAR", "Semestriel"), ("YEARLY", "Annuel"))),
        ):
            for order, (code, label) in enumerate(rows):
                session.add(model(code=code, label=label, sort_order=order))
                session.flush()
        session.commit()
        user_ids = {name: user.id for name, user in users.items()}

    def override_get_session() -> Generator:
        with session_factory() as session:
            try:
                yield session
                session.commit()
            except Exception:
                session.rollback()
                raise

    app.dependency_overrides[database.get_session] = override_get_session
    context = SimpleNamespace(
        engine=engine,
        session_factory=session_factory,
        user_ids=user_ids,
        tokens={"alice": "alice-test-token", "bob": "bob-test-token"},
    )
    try:
        yield context
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


@pytest.fixture
def client(request: pytest.FixtureRequest) -> Generator[TestClient, None, None]:
    request.getfixturevalue("test_context")
    yield TestClient(app)