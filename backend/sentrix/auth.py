from hashlib import sha256
from secrets import token_urlsafe
from typing import Annotated

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from sentrix.db import audit, engine, one, query

passwords = PasswordHasher()
dummy = passwords.hash(token_urlsafe(20))
bearer = HTTPBearer(auto_error=False)


def digest(value):
    return sha256(value.encode()).hexdigest()


def signin(login, password, correlation):
    with engine.begin() as conn:
        user = one(conn, "SELECT * FROM users WHERE login=:login", login=login)
        try:
            matched = passwords.verify(user["password"] if user else dummy, password)
        except VerifyMismatchError:
            matched = False
        if not user or not matched:
            raise HTTPException(401, "INVALID_CREDENTIALS")
        token = token_urlsafe(32)
        query(
            conn,
            "INSERT INTO sessions VALUES (:digest,:login,now()+interval '8 hours')",
            digest=digest(token),
            login=login,
        )
        audit(conn, login, correlation, "SIGN_IN", login)
        return {
            "token": token,
            "role": user["role"],
            "name": user["name"],
            "login": login,
        }


def identity(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
):
    if credentials:
        key = digest(credentials.credentials)
        with engine.connect() as conn:
            user = one(
                conn,
                """SELECT u.login,u.role,u.name FROM sessions s JOIN users u ON u.login=s.login
                    WHERE s.digest=:key AND s.expires>now()""",
                key=key,
            )
        if user:
            return {**user, "session": key}
    raise HTTPException(401, "AUTH_REQUIRED")


Actor = Annotated[dict, Depends(identity)]

OPERATIONS = ("FRAUD_ANALYST", "SENIOR_ANALYST", "FRAUD_MANAGER", "ADMIN")


def require(actor, *roles):
    if actor["role"] not in roles:
        raise HTTPException(403, "ROLE_FORBIDDEN")
