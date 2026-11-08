"""OIDC bearer-token authentication and role-based authorisation.

The API trusts only RS256 access tokens signed by the configured identity provider (Keycloak in this repo; any
OIDC provider such as Entra ID works the same way). It checks signature, expiry, issuer and audience, then reads
realm roles. Least privilege: `viewer` can read; only `engineer` can change state (acknowledge alerts).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

ROLE_VIEWER = "viewer"
ROLE_ENGINEER = "engineer"


@dataclass(frozen=True)
class Principal:
    subject: str
    username: str
    roles: frozenset[str]


KeyResolver = Callable[[str], Any]


class TokenVerifier:
    def __init__(self, issuer: str, audience: str, key_resolver: KeyResolver, leeway_s: int = 30):
        self.issuer = issuer
        self.audience = audience
        self.key_resolver = key_resolver
        self.leeway_s = leeway_s

    @classmethod
    def from_jwks(cls, issuer: str, audience: str, jwks_url: str) -> TokenVerifier:
        client = jwt.PyJWKClient(jwks_url, cache_keys=True, lifespan=600)
        return cls(issuer, audience, lambda token: client.get_signing_key_from_jwt(token).key)

    def verify(self, token: str) -> Principal:
        try:
            key = self.key_resolver(token)
            claims = jwt.decode(
                token,
                key=key,
                algorithms=["RS256"],
                audience=self.audience,
                issuer=self.issuer,
                leeway=self.leeway_s,
                options={"require": ["exp", "iat", "iss", "aud"]},
            )
        except jwt.PyJWTError as exc:
            raise HTTPException(
                status.HTTP_401_UNAUTHORIZED, f"invalid token: {exc}", headers={"WWW-Authenticate": "Bearer"}
            ) from exc
        roles = frozenset(claims.get("realm_access", {}).get("roles", []))
        return Principal(
            subject=str(claims.get("sub", "")),
            username=str(claims.get("preferred_username") or claims.get("sub") or "unknown"),
            roles=roles,
        )


_bearer = HTTPBearer(auto_error=False)


def current_principal(
    request: Request, creds: HTTPAuthorizationCredentials | None = Depends(_bearer)
) -> Principal:
    if creds is None or creds.scheme.lower() != "bearer":
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "missing bearer token", headers={"WWW-Authenticate": "Bearer"}
        )
    verifier: TokenVerifier = request.app.state.verifier
    return verifier.verify(creds.credentials)


def require_role(role: str) -> Callable[[Principal], Principal]:
    def _check(principal: Principal = Depends(current_principal)) -> Principal:
        if role not in principal.roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"requires role '{role}'")
        return principal

    return _check
