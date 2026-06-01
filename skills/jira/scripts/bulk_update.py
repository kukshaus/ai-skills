#!/usr/bin/env python3
"""Bulk-update issues matching a JQL. Dry-run by default; --apply to commit.

Safety limits:
  * Max 500 issues per run.
  * Max 5 concurrent requests.
  * 429/503 → exponential backoff (handled by jira_client.Jira).
"""
from __future__ import annotations

import argparse
import concurrent.futures
import json
import re
import sys

from jira_client import Jira, md_to_adf, resolve_auth, resolve_field_id

MAX_ISSUES = 500
MAX_WORKERS = 5


def _parse_set(spec: str) -> tuple[str, str, str]:
    m = re.match(r"^([^+\-=]+)(\+=|-=|=)(.*)$", spec)
    if not m:
        sys.exit(f"bad --set '{spec}' (expected name=value, name+=value, or name-=value)")
    return m.group(1).strip(), m.group(2), m.group(3).strip()


def _build_body(j: Jira, sets: list[tuple[str, str, str]]) -> dict:
    fields, update = {}, {}
    for name, op, value in sets:
        fid = resolve_field_id(j, name)
        if op == "=":
            if fid in {"description", "environment"}:
                fields[fid] = md_to_adf(value)
            elif fid in {"labels", "components", "fixVersions"}:
                fields[fid] = [v.strip() for v in value.split(",") if v.strip()]
            else:
                fields[fid] = value
        else:
            update.setdefault(fid, []).append({"add" if op == "+=" else "remove": value})
    body = {}
    if fields: body["fields"] = fields
    if update: body["update"] = update
    return body


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--base-url"); p.add_argument("--email"); p.add_argument("--token")
    p.add_argument("--pat"); p.add_argument("--oauth")
    p.add_argument("--jql", required=True)
    p.add_argument("--set", action="append", required=True, dest="sets",
                   help='e.g. "labels+=archived" or "priority=Low"')
    p.add_argument("--apply", action="store_true", help="actually write changes")
    args = p.parse_args()

    auth = resolve_auth(args)
    j = Jira(auth)

    parsed = [_parse_set(s) for s in args.sets]
    body = _build_body(j, parsed)

    issues = list(j.paginate_jql(args.jql, fields=["summary", "status"], limit=MAX_ISSUES + 1))
    if len(issues) > MAX_ISSUES:
        sys.exit(f"Refusing: query returned >{MAX_ISSUES} issues. Narrow the JQL.")
    keys = [i["key"] for i in issues]

    print(json.dumps({
        "jql": args.jql,
        "count": len(keys),
        "changes": body,
        "issues": keys,
        "applied": False,
    }, indent=2))
    if not args.apply:
        print("\n(dry-run — pass --apply to commit)", file=sys.stderr)
        return

    failures: list[dict] = []

    def _do(k: str) -> tuple[str, bool, str]:
        try:
            j.put(f"issue/{k}", json_body=body)
            return k, True, ""
        except SystemExit as e:
            return k, False, str(e)

    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        for key, ok, err in ex.map(_do, keys):
            if not ok:
                failures.append({"key": key, "error": err})

    print(json.dumps({
        "applied": True,
        "ok": len(keys) - len(failures),
        "failed": failures,
    }, indent=2))
    if failures:
        sys.exit(1)


if __name__ == "__main__":
    main()
