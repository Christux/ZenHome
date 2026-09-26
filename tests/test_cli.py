import pytest
from sqlalchemy import select

from app import cli
from app.models import Users


def test_user_management_commands(test_context, monkeypatch) -> None:
    monkeypatch.setattr(cli, "SessionLocal", test_context.session_factory)
    monkeypatch.setattr(cli, "initialize_database", lambda create_demo_user=False: None)

    token = cli.create_user("  Camille  ")
    users = cli.list_users()
    created_id, display_name, is_active = next(row for row in users if row[1] == "Camille")
    assert display_name == "Camille"
    assert is_active is True
    assert cli.get_user_token(created_id) == ("Camille", token)

    display_name, renewed_token = cli.renew_user_token(created_id)
    assert display_name == "Camille"
    assert renewed_token != token
    assert cli.get_user_token(created_id) == ("Camille", renewed_token)

    with test_context.session_factory() as session:
        assert session.scalar(select(Users.token).where(Users.id == created_id)) == renewed_token


def test_user_management_rejects_empty_or_unknown_users(test_context, monkeypatch) -> None:
    monkeypatch.setattr(cli, "SessionLocal", test_context.session_factory)
    monkeypatch.setattr(cli, "initialize_database", lambda create_demo_user=False: None)

    with pytest.raises(ValueError, match="ne peut pas être vide"):
        cli.create_user("   ")
    with pytest.raises(ValueError, match="Aucun utilisateur"):
        cli.get_user_token(999)
    with pytest.raises(ValueError, match="Aucun utilisateur"):
        cli.renew_user_token(999)
