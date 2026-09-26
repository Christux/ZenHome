"""Token authentication dependencies for API routes."""

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .database import get_session
from .models import Users


def get_current_user(
    token: str | None = Header(default=None, alias="X-Auth-Token"),
    db: Session = Depends(get_session),
) -> Users:
    """Resolves the active user associated with a permanent login token."""
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token de connexion requis.",
        )
    user = db.scalar(select(Users).where(Users.token == token, Users.is_active.is_(True)))
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token de connexion invalide.",
        )
    return user
