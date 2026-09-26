"""SQLite database access and SQLAlchemy session management."""

from collections.abc import Generator
import logging
from typing import Any

from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session, sessionmaker

from .globals import DATABASE_PATH, DATABASE_URL, ZENHOME_ENV
from .models import (
    Base,
    ItemStatuses,
    ItemTypes,
    NotificationStatuses,
    OccurrenceStatuses,
    RecurrenceRules,
    RecurrenceTypes,
    Users,
)


logger = logging.getLogger(__name__)

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
    echo=ZENHOME_ENV in {"development", "dev"},
    use_insertmanyvalues=False,
)


@event.listens_for(engine, "connect")
def enable_sqlite_foreign_keys(dbapi_connection: Any, _connection_record: object) -> None:
    """Enables foreign key constraints on each SQLite connection."""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def get_session() -> Generator[Session, None, None]:
    """Provides a SQLAlchemy session and always closes it after use."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def initialize_database() -> None:
    """Creates the schema and demo user if needed."""
    DATABASE_PATH.parent.mkdir(exist_ok=True)
    logger.info("Initializing SQLite database: %s", DATABASE_PATH)
    Base.metadata.create_all(engine)
    session = SessionLocal()
    try:
        dictionary_defaults = (
            (ItemTypes, (("NOTE", "Note", 10), ("CHECKLIST", "Checklist", 20), ("TASK", "Tâche", 30))),
            (ItemStatuses, (("TODO", "À faire", 10), ("IN_PROGRESS", "En cours", 20), ("DONE", "Terminée", 30), ("CANCELLED", "Annulée", 40))),
            (RecurrenceTypes, (("NONE", "Aucune", 0), ("DAILY", "Quotidien", 10), ("WEEKLY", "Hebdomadaire", 20), ("MONTHLY", "Mensuel", 30), ("QUARTERLY", "Trimestriel", 40), ("HALF_YEAR", "Semestriel", 50), ("YEARLY", "Annuel", 60))),
            (OccurrenceStatuses, (("PENDING", "À venir", 10), ("COMPLETED", "Terminée", 20), ("SKIPPED", "Ignorée", 30), ("CANCELLED", "Annulée", 40))),
            (NotificationStatuses, (("PENDING", "En attente", 10), ("SENT", "Envoyée", 20), ("FAILED", "Échec", 30), ("CANCELLED", "Annulée", 40))),
        )
        for model, defaults in dictionary_defaults:
            existing_codes = set(session.scalars(select(model.code)).all())
            for code, label, sort_order in defaults:
                if code not in existing_codes:
                    session.add(model(code=code, label=label, sort_order=sort_order))

        if session.scalar(select(Users.id).where(Users.email == "demo@zenhome.local")) is None:
            session.add(Users(email="demo@zenhome.local", display_name="Jean Dupont"))
            logger.info("Demo user created")
        if session.scalar(select(RecurrenceRules.id).limit(1)) is None:
            recurrence_types = {
                row.code: row for row in session.scalars(select(RecurrenceTypes)).all()
            }
            presets = (
                ("DAILY", "Every day", "DAILY"),
                ("WEEKLY", "Every week", "WEEKLY"),
                ("MONTHLY", "Every month", "MONTHLY"),
                ("YEARLY", "Every year", "YEARLY"),
            )
            for type_code, label, expression in presets:
                recurrence_type = recurrence_types.get(type_code)
                if recurrence_type is not None:
                    session.add(RecurrenceRules(
                        recurrence_type_id=recurrence_type.id,
                        label=label,
                        expression=expression,
                    ))
            logger.info("Default recurrence rules created")
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
