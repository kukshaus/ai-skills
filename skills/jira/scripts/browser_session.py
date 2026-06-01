#!/usr/bin/env python3
"""Reuse the user's logged-in Atlassian browser session as a last-resort auth.

Reads cookies for the host of JIRA_BASE_URL from any installed browser using the
`browser_cookie3` library. Returns a dict of cookie name → value for use in a
requests.Session.

If browser_cookie3 isn't installed or no cookies are found, returns {}.

CLI:
    python browser_session.py                       # prints cookie names (masked)
    python browser_session.py --probe               # makes a /myself request to confirm session
"""
from __future__ import annotations

import argparse
import os
import sys
from urllib.parse import urlparse

USEFUL = {
    "cloud.session.token", "cloud.session.token.v2",
    "atlassian.xsrf.token",
    "tenant.session.token",
    "JSESSIONID",
    "ajs_anonymous_id",
}


def load_cookies(base_url: str) -> dict:
    try:
        import browser_cookie3  # type: ignore
    except ImportError:
        return {}
    host = urlparse(base_url).hostname or ""
    if not host:
        return {}
    domains = [host, "atlassian.net", "atlassian.com", "id.atlassian.com"]
    out: dict[str, str] = {}
    for loader in (
        getattr(browser_cookie3, "chrome", None),
        getattr(browser_cookie3, "edge", None),
        getattr(browser_cookie3, "brave", None),
        getattr(browser_cookie3, "vivaldi", None),
        getattr(browser_cookie3, "arc", None),
        getattr(browser_cookie3, "firefox", None),
        getattr(browser_cookie3, "safari", None),
    ):
        if not loader:
            continue
        try:
            jar = loader()
        except Exception:
            continue
        for c in jar:
            if not c.domain:
                continue
            if not any(d in c.domain for d in domains):
                continue
            if c.name in USEFUL or c.name.startswith("cloud.session"):
                out[c.name] = c.value
    return out


def _mask(v: str) -> str:
    return f"{v[:4]}…{v[-4:]}" if len(v) > 12 else "…"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--probe", action="store_true")
    args = ap.parse_args()

    base = os.environ.get("JIRA_BASE_URL", "").rstrip("/")
    if not base:
        sys.exit("JIRA_BASE_URL not set.")
    cookies = load_cookies(base)
    if not cookies:
        sys.exit(
            "No browser cookies found.\n"
            "Install with: pip install browser_cookie3\n"
            "Then open Jira in your default browser and log in once."
        )
    if args.probe:
        import requests
        r = requests.get(
            f"{base}/rest/api/3/myself",
            cookies=cookies,
            headers={"X-Atlassian-Token": "no-check", "Accept": "application/json"},
            timeout=15,
        )
        if r.ok:
            me = r.json()
            print(f"OK as {me.get('displayName')} ({me.get('accountId')})")
        else:
            sys.exit(f"probe failed: HTTP {r.status_code} — log in to Jira in your browser and retry.")
        return
    for k, v in cookies.items():
        print(f"{k}\t{_mask(v)}")


if __name__ == "__main__":
    main()
