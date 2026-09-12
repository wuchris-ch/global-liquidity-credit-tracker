"""Local loopback access or verified OIDC identity plus database membership."""

import os
from dataclasses import dataclass
from urllib.parse import urlsplit

import jwt
from fastapi import HTTPException, Request


@dataclass(frozen=True)
class Principal:
    workspace: str
    subject: str
    role: str


class Auth:
    def __init__(self, control):
        self.control = control
        self.mode = os.getenv("RESEARCH_AUTH_MODE", "local")
        if self.mode not in ("local", "oidc"):
            raise ValueError("Invalid RESEARCH_AUTH_MODE")
        self.jwks = None
        if self.mode == "oidc":
            self.issuer = os.environ["OIDC_ISSUER"]
            self.audience = os.environ["OIDC_AUDIENCE"]
            jwks_url = os.environ["OIDC_JWKS_URL"]
            if not jwks_url.startswith("https://") or not self.issuer.startswith(
                "https://"
            ):
                raise ValueError("OIDC requires HTTPS")
            self.jwks = jwt.PyJWKClient(
                jwks_url, cache_jwk_set=True, lifespan=300, timeout=10
            )

    def principal(self, request: Request):
        if self.mode == "local":
            if request.client and request.client.host not in (
                "127.0.0.1",
                "::1",
                "testclient",
            ):
                raise HTTPException(
                    403, "Local research requires a loopback connection"
                )
            host = urlsplit("http://" + request.headers.get("host", "")).hostname
            origin = request.headers.get("origin")
            allowed_origins = {
                x.strip()
                for x in os.getenv(
                    "RESEARCH_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000"
                ).split(",")
            }
            if host not in ("localhost", "127.0.0.1", "::1", "testserver") or (
                origin and origin not in allowed_origins
            ):
                raise HTTPException(403, "Untrusted local origin")
            return Principal("personal", "local-user", "owner")
        bearer = request.headers.get("authorization", "")
        if not bearer.startswith("Bearer "):
            raise HTTPException(401, "Bearer token required")
        try:
            token = bearer[7:]
            key = self.jwks.get_signing_key_from_jwt(token)
            claims = jwt.decode(
                token,
                key.key,
                algorithms=["RS256"],
                audience=self.audience,
                issuer=self.issuer,
                options={"require": ["exp", "iat", "sub", "iss", "aud"]},
            )
            workspace = request.headers.get("x-workspace-id", "")
            membership = self.control.get(workspace, "member", claims["sub"])
            if not membership.get("active") or membership["role"] not in (
                "owner",
                "editor",
                "viewer",
            ):
                raise ValueError("Inactive membership")
            return Principal(workspace, claims["sub"], membership["role"])
        except (jwt.PyJWTError, KeyError, ValueError, TypeError):
            raise HTTPException(
                401, "Invalid identity or workspace membership"
            ) from None


def require_editor(principal):
    if principal.role not in ("owner", "editor"):
        raise HTTPException(403, "Editor role required")
