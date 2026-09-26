"""Command-line utilities for managing ZenHome."""

from __future__ import annotations

import argparse
import secrets
import sys

from sqlalchemy.exc import SQLAlchemyError

from .database import SessionLocal, initialize_database
from .models import Users


def create_user(display_name: str) -> str:
    """Create a user and return its login token."""
    display_name = display_name.strip()
    if not display_name:
        raise ValueError("Le nom d'affichage ne peut pas être vide.")

    initialize_database(create_demo_user=False)
    token = secrets.token_urlsafe(32)
    session = SessionLocal()
    try:
        session.add(Users(token=token, display_name=display_name))
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
    return token


def main() -> int:
    parser = argparse.ArgumentParser(prog="zenhome")
    subparsers = parser.add_subparsers(dest="command", required=True)
    create_user_parser = subparsers.add_parser(
        "create-user", help="Créer un utilisateur et afficher son token"
    )
    create_user_parser.add_argument("display_name", help="Nom affiché de l'utilisateur")
    args = parser.parse_args()

    try:
        token = create_user(args.display_name)
    except ValueError as error:
        parser.error(str(error))
    except SQLAlchemyError as error:
        print(f"Impossible de créer l'utilisateur : {error}", file=sys.stderr)
        return 1

    print(f"Utilisateur créé : {args.display_name.strip()}")
    print(f"Token : {token}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
