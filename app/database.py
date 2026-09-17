"""Accès à la base SQLite et gestion des sessions SQLAlchemy."""

from collections.abc import Generator
import logging

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from .globals import DATABASE_PATH, DATABASE_URL
from .models import Base, RecurrenceRules, RecurrenceTypes, Users


logger = logging.getLogger(__name__)

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
    use_insertmanyvalues=False,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def get_session() -> Generator[Session, None, None]:
    """Fournit une session SQLAlchemy puis la ferme toujours après usage."""
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
    """Crée le schéma et l’utilisateur de démonstration si nécessaire."""
    DATABASE_PATH.parent.mkdir(exist_ok=True)
    logger.info("Initialisation de la base SQLite: %s", DATABASE_PATH)
    Base.metadata.create_all(engine)
    session = SessionLocal()
    try:
        if session.scalar(select(Users.id).where(Users.email == "demo@zenhome.local")) is None:
            session.add(Users(email="demo@zenhome.local", display_name="Jean Dupont"))
            logger.info("Utilisateur de démonstration créé")
        if session.scalar(select(RecurrenceRules.id).limit(1)) is None:
            recurrence_types = {
                row.code: row for row in session.scalars(select(RecurrenceTypes)).all()
            }
            presets = (
                ("DAILY", "Chaque jour", "DAILY"),
                ("WEEKLY", "Chaque semaine", "WEEKLY"),
                ("MONTHLY", "Chaque mois", "MONTHLY"),
                ("YEARLY", "Chaque année", "YEARLY"),
            )
            for type_code, label, expression in presets:
                recurrence_type = recurrence_types.get(type_code)
                if recurrence_type is not None:
                    session.add(RecurrenceRules(
                        recurrence_type_id=recurrence_type.id,
                        label=label,
                        expression=expression,
                    ))
            logger.info("Règles de récurrence par défaut créées")
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
