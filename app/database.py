"""SQLite database access and SQLAlchemy session management."""

from collections.abc import Generator
import logging
from typing import Any

from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session, sessionmaker

from .globals import DATABASE_PATH, DATABASE_URL
from .models import Base, RecurrenceRules, RecurrenceTypes, Users


logger = logging.getLogger(__name__)

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
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
