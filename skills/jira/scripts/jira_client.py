#!/usr/bin/env python3
"""Jira client + CLI used by the rest of the scripts.

Resolves auth in this order:
  1. CLI flags
  2. Env JIRA_API_TOKEN + JIRA_EMAIL          (Cloud Basic)
  3. Env JIRA_OAUTH_TOKEN                     (OAuth 2.0)
  4. Env JIRA_PAT                             (Data Center)
  5. OS keychain  (service="jira", account=base_url)
  6. Browser session cookies via browser_session.py

All commands print JSON to stdout, errors to stderr, non-zero exit on failure.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

try:
    import requests
except ImportError:  # pragma: no cover
    sys.stderr.write("Missing dependency 'requests'. Run: pip install -r requirements.txt\n")
    sys.exit(2)

CACHE_DIR = Path(os.environ.get("JIRA_SKILL_CACHE_DIR", os.path.expanduser("~/.cache/jira-skill")))
DEFAULT_TIMEOUT = 30


# ---------- auth ----------------------------------------------------------- #

@dataclass
class Auth:
    base_url: str
    mode: str
    headers: dict = field(default_factory=dict)
    cookies: dict | None = None
    email: str | None = None

    def masked(self) -> str:
        tok = self.headers.get("Authorization", "")
        return f"{self.mode} …{tok[-4:]}" if tok else self.mode


def _from_keychain(base_url: str) -> tuple[str, str] | None:
    try:
        import keyring  # type: ignore
    except ImportError:
        return None
    try:
        raw = keyring.get_password("jira", base_url)
    except Exception:
        return None
    if not raw or ":" not in raw:
        return None
    email, token = raw.split(":", 1)
    return email, token


def resolve_auth(args: argparse.Namespace) -> Auth:
    base_url = (
        getattr(args, "base_url", None)
        or os.environ.get("JIRA_BASE_URL")
        or ""
    ).rstrip("/")
    if not base_url:
        sys.exit("error: JIRA_BASE_URL is not set and --base-url was not passed.")

    # 1. CLI flags
    if getattr(args, "token", None) and getattr(args, "email", None):
        return _basic(base_url, args.email, args.token)
    if getattr(args, "pat", None):
        return Auth(base_url, "pat", {"Authorization": f"Bearer {args.pat}"})
    if getattr(args, "oauth", None):
        return Auth(base_url, "oauth", {"Authorization": f"Bearer {args.oauth}"})

    # 2-4. Env vars
    email = os.environ.get("JIRA_EMAIL")
    token = os.environ.get("JIRA_API_TOKEN")
    if email and token:
        return _basic(base_url, email, token)
    if os.environ.get("JIRA_OAUTH_TOKEN"):
        return Auth(base_url, "oauth", {"Authorization": f"Bearer {os.environ['JIRA_OAUTH_TOKEN']}"})
    if os.environ.get("JIRA_PAT"):
        return Auth(base_url, "pat", {"Authorization": f"Bearer {os.environ['JIRA_PAT']}"})

    # 5. Keychain
    kc = _from_keychain(base_url)
    if kc:
        return _basic(base_url, kc[0], kc[1])

    # 6. Browser session
    try:
        from browser_session import load_cookies  # type: ignore
    except ImportError:
        from .browser_session import load_cookies  # type: ignore  # noqa: F401
    cookies = load_cookies(base_url)
    if cookies:
        return Auth(
            base_url,
            "browser-session",
            headers={"X-Atlassian-Token": "no-check"},
            cookies=cookies,
        )

    sys.exit(
        "error: no Jira credentials found. Set one of:\n"
        "  JIRA_EMAIL + JIRA_API_TOKEN  (Cloud)\n"
        "  JIRA_OAUTH_TOKEN             (OAuth 2.0)\n"
        "  JIRA_PAT                     (Data Center)\n"
        "  keyring set jira <base-url>  (interactive)\n"
        "  -- or -- log in to Jira in your default browser, then retry."
    )


def _basic(base_url: str, email: str, token: str) -> Auth:
    blob = base64.b64encode(f"{email}:{token}".encode()).decode()
    return Auth(base_url, "basic", {"Authorization": f"Basic {blob}"}, email=email)


# ---------- HTTP ----------------------------------------------------------- #

class Jira:
    def __init__(self, auth: Auth):
        self.auth = auth
        self.s = requests.Session()
        self.s.headers.update({"Accept": "application/json", **auth.headers})
        if auth.cookies:
            self.s.cookies.update(auth.cookies)
        self._api_version = "3"  # downgraded to "2" on DC

    def _url(self, path: str) -> str:
        if path.startswith("http"):
            return path
        if path.startswith("/"):
            return self.auth.base_url + path
        return f"{self.auth.base_url}/rest/api/{self._api_version}/{path}"

    def request(self, method: str, path: str, *, json_body: Any = None,
                params: dict | None = None, files=None, raw: bool = False) -> Any:
        url = self._url(path)
        for attempt in range(5):
            r = self.s.request(
                method, url,
                json=json_body, params=params, files=files,
                timeout=DEFAULT_TIMEOUT,
                headers={"Content-Type": "application/json"} if json_body and not files else None,
            )
            if r.status_code in (429, 503):
                wait = float(r.headers.get("Retry-After", 2 ** attempt))
                time.sleep(min(wait, 30))
                continue
            if not r.ok:
                self._raise(r)
            if raw:
                return r
            if not r.content:
                return None
            return r.json()
        sys.exit(f"error: {method} {url} retried 5x then failed.")

    @staticmethod
    def _raise(r: requests.Response) -> None:
        try:
            body = r.json()
        except Exception:
            body = r.text
        sys.stderr.write(f"HTTP {r.status_code} {r.request.method} {r.url}\n")
        sys.stderr.write(json.dumps(body, indent=2) if isinstance(body, (dict, list)) else str(body))
        sys.stderr.write("\n")
        sys.exit(1)

    # ---- helpers ---- #

    def get(self, path, **kw): return self.request("GET", path, **kw)
    def post(self, path, **kw): return self.request("POST", path, **kw)
    def put(self, path, **kw): return self.request("PUT", path, **kw)
    def delete(self, path, **kw): return self.request("DELETE", path, **kw)

    def paginate_jql(self, jql: str, fields: list[str] | None = None,
                     limit: int | None = None) -> Iterable[dict]:
        token = None
        seen = 0
        while True:
            body = {"jql": jql, "fields": fields or ["summary", "status"], "maxResults": 100}
            if token:
                body["nextPageToken"] = token
            res = self.post("search/jql", json_body=body)
            for issue in res.get("issues", []):
                yield issue
                seen += 1
                if limit and seen >= limit:
                    return
            token = res.get("nextPageToken")
            if not token:
                return


# ---------- Markdown → ADF (minimal) --------------------------------------- #

def md_to_adf(md: str) -> dict:
    """Convert a Markdown string to a minimal ADF document.

    Supports: headings, paragraphs, bullet/ordered lists, code blocks (fenced),
    bold (**), italic (*), inline code (`), and links [text](url).
    Anything else is rendered as plain text.
    """
    lines = md.splitlines()
    blocks: list[dict] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("```"):
            lang = line[3:].strip() or None
            buf: list[str] = []
            i += 1
            while i < len(lines) and not lines[i].startswith("```"):
                buf.append(lines[i])
                i += 1
            blocks.append({
                "type": "codeBlock",
                "attrs": {"language": lang} if lang else {},
                "content": [{"type": "text", "text": "\n".join(buf)}] if buf else [],
            })
            i += 1
            continue
        m = re.match(r"^(#{1,6})\s+(.*)$", line)
        if m:
            blocks.append({
                "type": "heading",
                "attrs": {"level": len(m.group(1))},
                "content": _inline(m.group(2)),
            })
            i += 1
            continue
        if re.match(r"^\s*[-*]\s+", line):
            items, i = _collect_list(lines, i, ordered=False)
            blocks.append({"type": "bulletList", "content": items})
            continue
        if re.match(r"^\s*\d+\.\s+", line):
            items, i = _collect_list(lines, i, ordered=True)
            blocks.append({"type": "orderedList", "content": items})
            continue
        if line.strip() == "":
            i += 1
            continue
        para_buf = [line]
        i += 1
        while i < len(lines) and lines[i].strip() and not _is_block_start(lines[i]):
            para_buf.append(lines[i])
            i += 1
        blocks.append({"type": "paragraph", "content": _inline(" ".join(para_buf))})
    return {"type": "doc", "version": 1, "content": blocks or [{"type": "paragraph", "content": []}]}


def _is_block_start(line: str) -> bool:
    return bool(
        line.startswith("```")
        or re.match(r"^#{1,6}\s", line)
        or re.match(r"^\s*[-*]\s", line)
        or re.match(r"^\s*\d+\.\s", line)
    )


def _collect_list(lines, i, ordered):
    items = []
    pat = re.compile(r"^\s*\d+\.\s+(.*)$") if ordered else re.compile(r"^\s*[-*]\s+(.*)$")
    while i < len(lines):
        m = pat.match(lines[i])
        if not m:
            break
        items.append({"type": "listItem",
                      "content": [{"type": "paragraph", "content": _inline(m.group(1))}]})
        i += 1
    return items, i


_INLINE = re.compile(
    r"(\*\*[^*]+\*\*|\*[^*]+\*|`[^`]+`|\[[^\]]+\]\([^)]+\))"
)


def _inline(text: str) -> list[dict]:
    out: list[dict] = []
    pos = 0
    for m in _INLINE.finditer(text):
        if m.start() > pos:
            out.append({"type": "text", "text": text[pos:m.start()]})
        chunk = m.group(0)
        if chunk.startswith("**"):
            out.append({"type": "text", "text": chunk[2:-2], "marks": [{"type": "strong"}]})
        elif chunk.startswith("`"):
            out.append({"type": "text", "text": chunk[1:-1], "marks": [{"type": "code"}]})
        elif chunk.startswith("["):
            label, url = re.match(r"\[([^\]]+)\]\(([^)]+)\)", chunk).groups()
            out.append({"type": "text", "text": label,
                        "marks": [{"type": "link", "attrs": {"href": url}}]})
        else:
            out.append({"type": "text", "text": chunk[1:-1], "marks": [{"type": "em"}]})
        pos = m.end()
    if pos < len(text):
        out.append({"type": "text", "text": text[pos:]})
    return out or [{"type": "text", "text": text}]


# ---------- field-map cache ------------------------------------------------ #

def cache_path(base_url: str) -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^a-z0-9]+", "_", base_url.lower())
    return CACHE_DIR / f"{safe}.json"


def load_field_map(jira: Jira) -> dict:
    p = cache_path(jira.auth.base_url)
    if p.exists() and time.time() - p.stat().st_mtime < 24 * 3600:
        return json.loads(p.read_text())
    fields = jira.get("field")
    by_name = {f["name"].lower(): f["id"] for f in fields}
    data = {"fields": fields, "by_name": by_name, "fetched_at": time.time()}
    p.write_text(json.dumps(data))
    return data


def resolve_field_id(jira: Jira, name_or_id: str) -> str:
    if name_or_id.startswith("customfield_") or name_or_id in {
        "summary", "description", "labels", "priority", "assignee", "reporter",
        "duedate", "fixVersions", "components", "versions", "environment",
        "issuetype", "project", "parent",
    }:
        return name_or_id
    fm = load_field_map(jira)
    fid = fm["by_name"].get(name_or_id.lower())
    if not fid:
        sys.exit(f"error: unknown field '{name_or_id}'. Run `jira_client.py fields` to list.")
    return fid


# ---------- CLI ------------------------------------------------------------ #

def main() -> None:
    p = argparse.ArgumentParser(prog="jira_client.py")
    p.add_argument("--base-url"); p.add_argument("--email"); p.add_argument("--token")
    p.add_argument("--pat"); p.add_argument("--oauth")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("doctor", help="probe site & auth, cache field map")
    sub.add_parser("fields", help="list all fields")
    sub.add_parser("myself", help="show current user")

    pm = sub.add_parser("meta"); pm.add_argument("--project", required=True)
    pm.add_argument("--issuetype", required=True)

    pu = sub.add_parser("update"); pu.add_argument("key")
    pu.add_argument("--field", action="append", default=[])

    pc = sub.add_parser("comment"); pc.add_argument("key"); pc.add_argument("--body", required=True)
    pl = sub.add_parser("link"); pl.add_argument("from_key", metavar="FROM")
    pl.add_argument("--type", required=True); pl.add_argument("--to", required=True)

    pa = sub.add_parser("attach"); pa.add_argument("key"); pa.add_argument("path")
    padf = sub.add_parser("adf"); padf.add_argument("markdown")

    pb = sub.add_parser("boards"); pb.add_argument("--project", required=True)
    ps = sub.add_parser("sprints"); ps.add_argument("--board", required=True, type=int)
    ps.add_argument("--state", default="active,future")

    psm = sub.add_parser("sprint-move"); psm.add_argument("--sprint", required=True, type=int)
    psm.add_argument("keys", nargs="+")

    pss = sub.add_parser("sprint-start"); pss.add_argument("--sprint", required=True, type=int)
    pss.add_argument("--start", required=True); pss.add_argument("--end", required=True)
    pss.add_argument("--goal", default="")

    psc = sub.add_parser("sprint-complete"); psc.add_argument("--sprint", required=True, type=int)
    psc.add_argument("--confirm", action="store_true")

    pal = sub.add_parser("atlas-link"); pal.add_argument("--issue", required=True)
    pal.add_argument("--goal-key"); pal.add_argument("--project-key")

    pr = sub.add_parser("rovo-summarize"); pr.add_argument("key")
    prd = sub.add_parser("rovo-draft"); prd.add_argument("--project", required=True)
    prd.add_argument("--issuetype", required=True); prd.add_argument("--prompt", required=True)

    pau = sub.add_parser("automation"); pau.add_argument("action", choices=["list", "trigger", "history", "toggle"])
    pau.add_argument("--rule"); pau.add_argument("--issue"); pau.add_argument("--issues")
    pau.add_argument("--webhook"); pau.add_argument("--data"); pau.add_argument("--enabled")

    args = p.parse_args()
    auth = resolve_auth(args)
    j = Jira(auth)

    # DC fallback detection
    me = None
    try:
        me = j.get("myself")
    except SystemExit:
        j._api_version = "2"
        me = j.get("myself")

    if args.cmd == "doctor":
        print(json.dumps({
            "base_url": auth.base_url,
            "auth": auth.masked(),
            "api_version": j._api_version,
            "user": me.get("displayName") or me.get("name"),
            "accountId": me.get("accountId"),
            "field_cache": str(cache_path(auth.base_url)),
        }, indent=2))
        load_field_map(j)
        return

    if args.cmd == "fields":
        print(json.dumps(load_field_map(j)["fields"], indent=2))
        return

    if args.cmd == "myself":
        print(json.dumps(me, indent=2))
        return

    if args.cmd == "meta":
        res = j.get(f"issue/createmeta/{args.project}/issuetypes")
        types = {t["name"]: t for t in res.get("issueTypes", res.get("values", []))}
        it = types.get(args.issuetype)
        if not it:
            sys.exit(f"error: issuetype '{args.issuetype}' not on project {args.project}. Available: {list(types)}")
        print(json.dumps(j.get(f"issue/createmeta/{args.project}/issuetypes/{it['id']}"), indent=2))
        return

    if args.cmd == "update":
        body = _build_update(j, args.field)
        j.put(f"issue/{args.key}", json_body=body)
        print(json.dumps({"key": args.key, "url": f"{auth.base_url}/browse/{args.key}", "ok": True}))
        return

    if args.cmd == "comment":
        j.post(f"issue/{args.key}/comment", json_body={"body": md_to_adf(args.body)})
        print(json.dumps({"key": args.key, "url": f"{auth.base_url}/browse/{args.key}", "ok": True}))
        return

    if args.cmd == "link":
        j.post("issueLink", json_body={
            "type": {"name": args.type},
            "inwardIssue": {"key": args.from_key},
            "outwardIssue": {"key": args.to},
        })
        print(json.dumps({"ok": True}))
        return

    if args.cmd == "attach":
        with open(args.path, "rb") as fh:
            r = j.s.post(
                j._url(f"issue/{args.key}/attachments"),
                headers={**auth.headers, "X-Atlassian-Token": "no-check"},
                files={"file": (Path(args.path).name, fh)},
                cookies=auth.cookies,
                timeout=DEFAULT_TIMEOUT,
            )
        if not r.ok:
            sys.exit(f"attach failed: HTTP {r.status_code} {r.text}")
        print(json.dumps(r.json()))
        return

    if args.cmd == "adf":
        print(json.dumps(md_to_adf(args.markdown), indent=2))
        return

    if args.cmd == "boards":
        print(json.dumps(j.get(f"{auth.base_url}/rest/agile/1.0/board", params={"projectKeyOrId": args.project})))
        return
    if args.cmd == "sprints":
        print(json.dumps(j.get(
            f"{auth.base_url}/rest/agile/1.0/board/{args.board}/sprint",
            params={"state": args.state})))
        return
    if args.cmd == "sprint-move":
        j.post(f"{auth.base_url}/rest/agile/1.0/sprint/{args.sprint}/issue",
               json_body={"issues": args.keys})
        print(json.dumps({"moved": args.keys, "sprint": args.sprint})); return
    if args.cmd == "sprint-start":
        j.post(f"{auth.base_url}/rest/agile/1.0/sprint/{args.sprint}",
               json_body={"state": "active", "startDate": args.start, "endDate": args.end, "goal": args.goal})
        print(json.dumps({"sprint": args.sprint, "state": "active"})); return
    if args.cmd == "sprint-complete":
        if not args.confirm:
            sys.exit("Refusing to complete sprint without --confirm.")
        j.post(f"{auth.base_url}/rest/agile/1.0/sprint/{args.sprint}", json_body={"state": "closed"})
        print(json.dumps({"sprint": args.sprint, "state": "closed"})); return

    if args.cmd == "atlas-link":
        sys.exit("atlas-link requires OAuth and a workspaceUuid — open premium-features.md → Atlas for the GraphQL payload to fill in.")

    if args.cmd == "rovo-summarize":
        try:
            out = j.post(f"issue/{args.key}/summary")
        except SystemExit:
            sys.exit("Rovo summarize endpoint not available on this tenant.")
        print(json.dumps(out)); return
    if args.cmd == "rovo-draft":
        try:
            out = j.post("ai/issue/draft", json_body={
                "project": args.project, "issuetype": args.issuetype, "prompt": args.prompt})
        except SystemExit:
            sys.exit("Rovo draft endpoint not available on this tenant.")
        print(json.dumps(out)); return

    if args.cmd == "automation":
        a = args.action
        if a == "list":
            print(json.dumps(j.get("automation/rule"))); return
        if a == "trigger":
            if args.webhook:
                payload = {"issues": (args.issues or args.issue or "").split(",")}
                if args.data:
                    payload["data"] = json.loads(args.data)
                r = requests.post(args.webhook, json=payload, timeout=DEFAULT_TIMEOUT)
                if not r.ok: sys.exit(f"webhook failed: {r.status_code} {r.text}")
                print(json.dumps({"ok": True})); return
            j.post(f"automation/rule/{args.rule}/execution",
                   json_body={"issues": [args.issue]} if args.issue else None)
            print(json.dumps({"ok": True})); return
        sys.exit(f"automation '{a}' not implemented in v1")


def _build_update(j: Jira, raw: list[str]) -> dict:
    fields: dict = {}
    update: dict = {}
    for spec in raw:
        m = re.match(r"^([^+\-=]+)(\+=|-=|=)(.*)$", spec)
        if not m:
            sys.exit(f"bad --field '{spec}' (expected name=value or name+=value)")
        name, op, value = m.group(1).strip(), m.group(2), m.group(3).strip()
        fid = resolve_field_id(j, name)
        if op == "=":
            fields[fid] = _coerce(fid, value)
        else:
            update.setdefault(fid, []).append({"add" if op == "+=" else "remove": value})
    body: dict = {}
    if fields: body["fields"] = fields
    if update: body["update"] = update
    return body


def _coerce(fid: str, value: str):
    if fid in {"labels", "components", "fixVersions", "versions"}:
        return [v.strip() for v in value.split(",") if v.strip()]
    if fid in {"description", "environment"} or fid.startswith("customfield_"):
        if value.startswith("{"):
            try: return json.loads(value)
            except Exception: pass
        return md_to_adf(value) if fid in {"description", "environment"} else value
    if fid == "assignee":
        return {"accountId": value} if value != "unassigned" else None
    if fid in {"priority", "issuetype", "resolution"}:
        return {"name": value}
    if fid in {"project", "parent"}:
        return {"key": value}
    return value


if __name__ == "__main__":
    main()
