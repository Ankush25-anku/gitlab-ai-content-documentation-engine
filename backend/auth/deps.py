"""Authentication and role-based access control.

AUTH_MODE=dev       -> "Authorization: Bearer demo:<role>" logs in as the seeded demo user for that role.
                       Never enable in production (the app refuses to start with dev auth when APP_ENV=production).
AUTH_MODE=supabase  -> verifies the Supabase access token (HS256 legacy secret, or the project's JWKS)
                       and loads the role from the profiles table.
"""
from functools import lru_cache

import jwt
from fastapi import Depends, Header
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.config import get_settings
from backend.database.models import Profile
from backend.database.session import get_db
from backend.services.errors import AppError

ROLES = ("creator", "tech_reviewer", "doc_lead", "publisher", "admin")
DEMO_USERS = {
    "creator": ("demo-creator", "creator@example.com", "Priya (Content Creator)"),
    "tech_reviewer": ("demo-reviewer", "reviewer@example.com", "Arjun (Technical Reviewer)"),
    "doc_lead": ("demo-doclead", "doclead@example.com", "Meera (Documentation Lead)"),
    "publisher": ("demo-publisher", "publisher@example.com", "Rahul (Publisher)"),
    "admin": ("demo-admin", "admin@example.com", "Admin"),
}


def ensure_demo_users(db: Session) -> None:
    for role, (uid, email, name) in DEMO_USERS.items():
        if db.get(Profile, uid) is None:
            db.add(Profile(id=uid, email=email, name=name, role=role))
    db.commit()


@lru_cache
def _jwks_client(url: str) -> jwt.PyJWKClient:
    return jwt.PyJWKClient(f"{url.rstrip('/')}/auth/v1/.well-known/jwks.json")


def _decode_supabase(token: str) -> dict:
    s = get_settings()
    try:
        if s.supabase_jwt_secret:
            return jwt.decode(token, s.supabase_jwt_secret, algorithms=["HS256"], audience="authenticated")
        key = _jwks_client(s.supabase_url).get_signing_key_from_jwt(token).key
        return jwt.decode(token, key, algorithms=["RS256", "ES256"], audience="authenticated")
    except jwt.PyJWTError as exc:
        raise AppError("UNAUTHORIZED", f"Invalid or expired token: {exc}") from exc


def get_current_user(authorization: str | None = Header(default=None), db: Session = Depends(get_db)) -> Profile:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise AppError("UNAUTHORIZED", "Missing bearer token.")
    token = authorization.split(" ", 1)[1].strip()
    settings = get_settings()

    if settings.auth_mode == "dev":
        if not token.startswith("demo:"):
            raise AppError("UNAUTHORIZED", "Dev auth expects a token of the form demo:<role>.")
        role = token.split(":", 1)[1]
        if role not in DEMO_USERS:
            raise AppError("UNAUTHORIZED", f"Unknown demo role '{role}'.")
        user = db.get(Profile, DEMO_USERS[role][0])
        if user is None:
            ensure_demo_users(db)
            user = db.get(Profile, DEMO_USERS[role][0])
        return user

    claims = _decode_supabase(token)
    user = db.get(Profile, claims["sub"])
    if user is None:  # first login: create a least-privilege profile; an admin can promote it
        email = claims.get("email", f"{claims['sub']}@unknown")
        existing = db.scalars(select(Profile).where(Profile.email == email)).first()
        if existing:
            return existing
        user = Profile(id=claims["sub"], email=email, name=email.split("@")[0], role="creator")
        db.add(user)
        db.commit()
    return user


def require_role(*roles: str):
    def checker(user: Profile = Depends(get_current_user)) -> Profile:
        if user.role != "admin" and user.role not in roles:
            raise AppError("FORBIDDEN", f"Role '{user.role}' cannot perform this action (needs one of {', '.join(roles)}).")
        return user
    return checker


STAFF = ("tech_reviewer", "doc_lead", "publisher", "admin")


def can_view_job(user: Profile, owner_id: str) -> bool:
    return user.id == owner_id or user.role in STAFF
