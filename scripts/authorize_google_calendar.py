#!/usr/bin/env python3
"""Create/exchange a Google OAuth token for calendar-view Google Calendar sync.

Usage:
  python scripts/authorize_google_calendar.py --url
  python scripts/authorize_google_calendar.py --code 'PASTE_CODE_HERE'

The resulting authorized-user token is written to:
  ../.secrets/google-calendar-token.json
"""
from __future__ import annotations

import argparse
import json
import os
import secrets
import sys
import urllib.parse
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parent
SECRETS = WORKSPACE / ".secrets"
DEFAULT_CLIENT_SECRET = Path.home() / ".config" / "ghealth" / "client_secret.json"
STATE_PATH = SECRETS / "google-calendar-auth-state.json"
TOKEN_PATH = SECRETS / "google-calendar-token.json"
SCOPE = "https://www.googleapis.com/auth/calendar.events"
REDIRECT_URI = "http://localhost:8765/"
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"


def load_client(path: Path) -> dict[str, str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    client = data.get("installed") or data.get("web") or data
    if not client.get("client_id") or not client.get("client_secret"):
        raise RuntimeError(f"Client secret file {path} does not contain client_id/client_secret")
    return client


def make_url(client_secret_path: Path) -> str:
    client = load_client(client_secret_path)
    state = secrets.token_urlsafe(24)
    SECRETS.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(
        json.dumps(
            {
                "state": state,
                "client_secret_path": str(client_secret_path),
                "redirect_uri": REDIRECT_URI,
                "scope": SCOPE,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    params = {
        "client_id": client["client_id"],
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": SCOPE,
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
        "include_granted_scopes": "true",
    }
    return f"{AUTH_URL}?{urllib.parse.urlencode(params)}"


def exchange_code(code_or_url: str) -> Path:
    if not STATE_PATH.exists():
        raise RuntimeError("No auth state file found. Run --url first.")
    state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    client = load_client(Path(state["client_secret_path"]))

    value = code_or_url.strip()
    parsed = urllib.parse.urlparse(value)
    if parsed.query:
        query = urllib.parse.parse_qs(parsed.query)
        returned_state = query.get("state", [None])[0]
        if returned_state and returned_state != state["state"]:
            raise RuntimeError("OAuth state mismatch; refusing to exchange code")
        value = query.get("code", [value])[0]
    code = urllib.parse.unquote(value)

    response = requests.post(
        TOKEN_URL,
        data={
            "client_id": client["client_id"],
            "client_secret": client["client_secret"],
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": state["redirect_uri"],
        },
        timeout=30,
    )
    if response.status_code >= 400:
        raise RuntimeError(f"Token exchange failed: {response.status_code} {response.text}")
    token = response.json()
    token_out = {
        "client_id": client["client_id"],
        "client_secret": client["client_secret"],
        "refresh_token": token.get("refresh_token"),
        "token": token.get("access_token"),
        "token_uri": TOKEN_URL,
        "scopes": token.get("scope", SCOPE).split(),
    }
    if not token_out["refresh_token"]:
        # Existing consent can sometimes suppress refresh_token; prompt=consent normally avoids that.
        raise RuntimeError("Token exchange succeeded but no refresh_token was returned; rerun --url and approve consent again")
    SECRETS.mkdir(parents=True, exist_ok=True)
    TOKEN_PATH.write_text(json.dumps(token_out, indent=2), encoding="utf-8")
    os.chmod(TOKEN_PATH, 0o600)
    try:
        STATE_PATH.unlink()
    except FileNotFoundError:
        pass
    return TOKEN_PATH


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", action="store_true", help="print Google consent URL")
    parser.add_argument("--code", help="authorization code, or the final localhost redirect URL containing code=")
    parser.add_argument("--client-secret", type=Path, default=DEFAULT_CLIENT_SECRET)
    args = parser.parse_args()

    if args.url == bool(args.code):
        parser.error("use exactly one of --url or --code")
    if args.url:
        print(make_url(args.client_secret))
    else:
        path = exchange_code(args.code or "")
        print(f"Wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
