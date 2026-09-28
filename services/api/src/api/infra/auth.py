"""JWT validation against Keycloak's JWKS (PLAN §2 "Auth": Keycloak OIDC,
JWT validation via JWKS). Tenant and role are read straight off the
validated token's claims (CLAUDE.md: "Tenant/role always comes from the JWT
server-side") — `infra/keycloak/fleetpulse-realm.json`'s protocol mappers
put them at `tenant` and `realm_access.roles`.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

import jwt
from fastapi import HTTPException, status

_jwks_client: jwt.PyJWKClient | None = None


def _jwks_url() -> str:
    host = os.environ.get("KEYCLOAK_HOST", "localhost")
    port = os.environ.get("KEYCLOAK_INTERNAL_PORT", "8080")
    realm = os.environ.get("KEYCLOAK_REALM", "fleetpulse")
    return f"http://{host}:{port}/realms/{realm}/protocol/openid-connect/certs"


def _get_jwks_client() -> jwt.PyJWKClient:
    global _jwks_client
    if _jwks_client is None:
        # lifespan_secs=3600 (PyJWT default): caches signing keys, so a
        # verify-per-request doesn't re-fetch Keycloak's JWKS every time.
        _jwks_client = jwt.PyJWKClient(_jwks_url())
    return _jwks_client


@dataclass(frozen=True)
class CurrentUser:
    sub: str
    email: str
    tenant: str
    roles: list[str]


def decode_token(token: str) -> CurrentUser:
    try:
        signing_key = _get_jwks_client().get_signing_key_from_jwt(token)
        # verify_iss is intentionally off: the token's `iss` reflects whatever
        # host/port the client used to reach Keycloak (localhost:8082 from a
        # browser vs keycloak:8080 from inside the compose network), which
        # differ in this POC's dev setup. Documented trimmed-scope decision,
        # not an oversight — signature + expiry are still fully verified.
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            options={"verify_aud": False, "verify_iss": False},
        )
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=f"invalid token: {exc}"
        ) from exc

    tenant = claims.get("tenant")
    roles = claims.get("realm_access", {}).get("roles", [])
    if not tenant:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="token missing tenant claim")

    return CurrentUser(
        sub=claims["sub"],
        email=claims.get("email", claims.get("preferred_username", claims["sub"])),
        tenant=tenant,
        roles=roles,
    )
