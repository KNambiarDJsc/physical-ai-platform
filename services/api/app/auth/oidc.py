"""OIDC access-token validation (the API is a resource server; it never runs a login flow).

Checks signature against the issuer's JWKS, ``iss``, ``aud``, ``exp`` (and ``nbf``/``iat`` when present), requires
``sub``, and accepts only asymmetric algorithms from configuration, so ``none`` and HS256-with-a-public-key are
refused by construction.
"""

from __future__ import annotations

import json
import urllib.request
from functools import lru_cache
from typing import Any

import jwt
from jwt import PyJWKClient

ASYMMETRIC = {"RS256", "RS384", "RS512", "PS256", "PS384", "PS512", "ES256", "ES384", "ES512", "EdDSA"}


class TokenInvalid(Exception):
    pass


def discover_jwks_url(issuer: str, timeout_s: float = 5.0) -> str:
    url = issuer.rstrip("/") + "/.well-known/openid-configuration"
    if not url.startswith(("https://", "http://127.0.0.1", "http://localhost")):
        raise TokenInvalid("issuer must use https")
    with urllib.request.urlopen(url, timeout=timeout_s) as r:  # noqa: S310 (scheme checked above)
        doc: dict[str, Any] = json.loads(r.read(1_000_000))
    jwks = doc.get("jwks_uri")
    if not isinstance(jwks, str):
        raise TokenInvalid("issuer metadata has no jwks_uri")
    return jwks


class OidcVerifier:
    def __init__(self, issuer: str, audience: str, jwks_url: str | None, algorithms: list[str]) -> None:
        bad = [a for a in algorithms if a not in ASYMMETRIC]
        if bad:
            raise ValueError(f"only asymmetric signature algorithms are allowed, not {bad}")
        self.issuer = issuer
        self.audience = audience
        self.algorithms = algorithms
        self._jwks_url = jwks_url
        self._client: PyJWKClient | None = None

    def _keys(self) -> PyJWKClient:
        if self._client is None:
            url = self._jwks_url or discover_jwks_url(self.issuer)
            self._client = PyJWKClient(url, cache_keys=True, lifespan=300, timeout=5)
        return self._client

    def verify(self, token: str) -> dict[str, Any]:
        try:
            key = self._keys().get_signing_key_from_jwt(token)
            claims: dict[str, Any] = jwt.decode(
                token,
                key.key,
                algorithms=self.algorithms,
                audience=self.audience,
                issuer=self.issuer,
                options={"require": ["exp", "iss", "aud", "sub"]},
                leeway=30,
            )
        except (jwt.PyJWTError, OSError) as e:
            raise TokenInvalid(type(e).__name__) from e
        if not isinstance(claims.get("sub"), str) or not claims["sub"]:
            raise TokenInvalid("sub missing")
        return claims


@lru_cache(maxsize=4)
def verifier(issuer: str, audience: str, jwks_url: str | None, algorithms: tuple[str, ...]) -> OidcVerifier:
    return OidcVerifier(issuer, audience, jwks_url, list(algorithms))
