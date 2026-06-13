"""Authlib Google OAuth client wiring.

We register the Google provider using OpenID Connect discovery so token + userinfo
endpoints stay correct. Credentials come from the parsed ``OAUTH_CLIENT_JSON``.
"""

from __future__ import annotations

from authlib.integrations.starlette_client import OAuth

from web_api.config import Settings

GOOGLE_DISCOVERY = "https://accounts.google.com/.well-known/openid-configuration"


def build_oauth(settings: Settings) -> OAuth:
    oauth = OAuth()
    if not settings.google:
        return oauth
    oauth.register(
        name="google",
        client_id=settings.google.client_id,
        client_secret=settings.google.client_secret,
        server_metadata_url=GOOGLE_DISCOVERY,
        client_kwargs={"scope": "openid email profile"},
    )
    return oauth
