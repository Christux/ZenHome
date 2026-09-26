"""Command-line utilities for managing ZenHome."""

from __future__ import annotations

import argparse
import secrets
import sys

from sqlalchemy import select
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


def get_user_token(user_id: int) -> tuple[str, str]:
    """Return a user's display name and login token."""
    with SessionLocal() as session:
        user = session.scalar(select(Users).where(Users.id == user_id))
        if user is None:
            raise ValueError(f"Aucun utilisateur avec l'identifiant {user_id}.")
        return user.display_name, user.token


def renew_user_token(user_id: int) -> tuple[str, str]:
    """Replace a user's login token and return the new token."""
    session = SessionLocal()
    try:
        user = session.scalar(select(Users).where(Users.id == user_id))
        if user is None:
            raise ValueError(f"Aucun utilisateur avec l'identifiant {user_id}.")
        user.token = secrets.token_urlsafe(32)
        session.commit()
        return user.display_name, user.token
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def list_users() -> list[tuple[int, str, bool]]:
    """Return user IDs, display names, and active states."""
    with SessionLocal() as session:
        users = session.scalars(select(Users).order_by(Users.id)).all()
        return [(user.id, user.display_name, user.is_active) for user in users]


def main() -> int:
    parser = argparse.ArgumentParser(prog="zenhome")
    subparsers = parser.add_subparsers(dest="command", required=True)
    create_user_parser = subparsers.add_parser(
        "create-user", help="Créer un utilisateur et afficher son token"
    )
    create_user_parser.add_argument("display_name", help="Nom affiché de l'utilisateur")
    show_token_parser = subparsers.add_parser(
        "show-token", help="Afficher le token d'un utilisateur"
    )
    show_token_parser.add_argument("user_id", type=int, help="Identifiant de l'utilisateur")
    subparsers.add_parser("list-users", help="Lister les utilisateurs")
    renew_token_parser = subparsers.add_parser(
        "renew-token", help="Renouveler le token d'un utilisateur"
    )
    renew_token_parser.add_argument("user_id", type=int, help="Identifiant de l'utilisateur")
    args = parser.parse_args()

    try:
        if args.command == "create-user":
            token = create_user(args.display_name)
        elif args.command == "show-token":
            display_name, token = get_user_token(args.user_id)
        elif args.command == "renew-token":
            display_name, token = renew_user_token(args.user_id)
        else:
            users = list_users()
    except ValueError as error:
        parser.error(str(error))
    except SQLAlchemyError as error:
        print(f"Erreur lors de l'accès aux utilisateurs : {error}", file=sys.stderr)
        return 1

    if args.command == "create-user":
        print(f"Utilisateur créé : {args.display_name.strip()}")
        print(f"Token : {token}")
    elif args.command == "show-token":
        print(f"Utilisateur : {display_name} (ID {args.user_id})")
        print(f"Token : {token}")
    elif args.command == "renew-token":
        print(f"Token renouvelé pour {display_name} (ID {args.user_id})")
        print(f"Nouveau token : {token}")
    elif users:
        print("ID\tNom\tÉtat")
        for user_id, display_name, is_active in users:
            state = "actif" if is_active else "inactif"
            print(f"{user_id}\t{display_name}\t{state}")
    else:
        print("Aucun utilisateur.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
