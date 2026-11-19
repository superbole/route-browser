"""Garmin Connect Personal API: token exchange + GET, for the route browser.

Key: GARMIN_PERSONAL_API_KEY (env var or .env), made at connect.garmin.com/app/settings/personalApiToken. Terms: the key holder's own use only. Read-only. No published rate limits, so callers
go slowly and cache.
"""
import os
import requests

BASE = os.environ.get("GARMIN_PERSONAL_API_BASE_URL", "https://personal.connectapi.garmin.com").rstrip("/")
TOKEN_PATH = "/personalapitoken-service/personal-api/personal-api-key/token"


def _api_key():
    """The env var, else a .env in or above the current folder (python-dotenv is optional)."""
    key = os.environ.get("GARMIN_PERSONAL_API_KEY")
    if not key:
        try:
            from dotenv import find_dotenv, load_dotenv
            load_dotenv(find_dotenv(usecwd=True))
            key = os.environ.get("GARMIN_PERSONAL_API_KEY")
        except ImportError:
            pass
    if not key:
        raise SystemExit("GARMIN_PERSONAL_API_KEY is not set (env var or .env). See README.md beside this file.")
    return key


class Garmin:
    def __init__(self):
        r = requests.post(BASE + TOKEN_PATH, headers={"Authorization": f"ApiKey {_api_key()}"}, timeout=30)
        if r.status_code in (401, 403):
            raise SystemExit(f"Garmin refused the key ({r.status_code}): it may have expired. "
                             "Make a new one: README.md, The Garmin key.")
        r.raise_for_status()
        body = r.json() if "json" in r.headers.get("Content-Type", "") else {}
        token = body.get("access_token") or body.get("accessToken") or body.get("token") or r.text.strip()
        self.s = requests.Session()
        self.s.headers["Authorization"] = f"Bearer {token}"

    def get(self, path, accept="application/json", **params):
        r = self.s.get(BASE + path, params=params, headers={"Accept": accept}, timeout=60)
        r.raise_for_status()
        return r.json() if accept == "application/json" else r.content
