"""Checks that a request comes from the signed-in Supabase user it asks about."""

from __future__ import annotations

import logging
from typing import Protocol

import jwt
from fastapi import HTTPException, Request, status

logger = logging.getLogger(__name__)

# Supabase signs access tokens with the project's asymmetric key.
ALGORITHMS = ["ES256", "RS256"]
AUDIENCE = "authenticated"


class InvalidToken(Exception):
    pass


class TokenVerifier(Protocol):
    def user_id(self, token: str) -> str:
        """The id of the user the access token belongs to. Raises InvalidToken."""


class SupabaseTokenVerifier:
    """Verifies access tokens against the project's published signing keys."""

    def __init__(self, supabase_url: str) -> None:
        self._issuer = f"{supabase_url.rstrip('/')}/auth/v1"
        self._keys = jwt.PyJWKClient(f"{self._issuer}/.well-known/jwks.json", cache_keys=True)

    def user_id(self, token: str) -> str:
        try:
            key = self._keys.get_signing_key_from_jwt(token)
            claims = jwt.decode(token, key.key, algorithms=ALGORITHMS, audience=AUDIENCE, issuer=self._issuer)
        except jwt.PyJWTError as exc:
            raise InvalidToken(str(exc)) from exc
        return str(claims["sub"])


def authorize(verifier: TokenVerifier | None, request: Request, user_id: str) -> None:
    """Allow the request only if its bearer token belongs to `user_id`.

    With no verifier (SUPABASE_URL unset) every request is allowed: local development only.
    """
    if verifier is None:
        return
    scheme, _, token = request.headers.get("authorization", "").partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "sign in to use this service",
                            headers={"WWW-Authenticate": "Bearer"})
    try:
        signed_in = verifier.user_id(token.strip())
    except InvalidToken:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "your session is not valid; sign in again",
                            headers={"WWW-Authenticate": "Bearer"})
    if signed_in != user_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "you can only use your own data")
