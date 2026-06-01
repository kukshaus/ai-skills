#!/usr/bin/env python3
"""Run a JQL query against Jira and print issues as JSON or a compact table.

Uses POST /rest/api/3/search/jql with cursor pagination. Falls back to the
legacy /search endpoint on Data Center.
"""
from __future__ import annotations

import argparse
import json
import sys

from jira_client import Jira, resolve_auth


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--base-url"); p.add_argument("--email"); p.add_argument("--token")
    p.add_argument("--pat"); p.add_argument("--oauth")
    p.add_argument("--jql"); p.add_argument("--filter", type=int,
                                            help="saved filter ID")
    p.add_argument("--fields", default="summary,status,assignee,priority,updated")
    p.add_argument("--limit", type=int, default=100)
    p.add_argument("--format", choices=["json", "table"], default="json")
    p.add_argument("--validate", action="store_true",
                   help="just parse-check the JQL, don't fetch results")
    args = p.parse_args()

    auth = resolve_auth(args)
    j = Jira(auth)

    if args.filter:
        f = j.get(f"filter/{args.filter}")
        jql = f["jql"]
    elif args.jql:
        jql = args.jql
    else:
        sys.exit("Provide --jql or --filter.")

    if args.validate:
        try:
            j.post("jql/parse", json_body={"queries": [jql]})
            print(json.dumps({"jql": jql, "valid": True}))
        except SystemExit:
            sys.exit(1)
        return

    field_list = [f.strip() for f in args.fields.split(",") if f.strip()]
    issues = list(j.paginate_jql(jql, fields=field_list, limit=args.limit))

    if args.format == "table":
        _print_table(issues, field_list, auth.base_url)
    else:
        print(json.dumps({"jql": jql, "count": len(issues), "issues": issues}, indent=2))


def _print_table(issues, fields, base_url):
    rows = []
    for i in issues:
        row = {"key": i["key"], "url": f"{base_url}/browse/{i['key']}"}
        f = i.get("fields", {})
        for name in fields:
            v = f.get(name)
            if isinstance(v, dict):
                row[name] = v.get("name") or v.get("displayName") or v.get("value") or str(v)
            else:
                row[name] = v
        rows.append(row)
    headers = ["key"] + fields
    widths = {h: max(len(h), *(len(str(r.get(h, ""))) for r in rows)) for h in headers}
    print(" | ".join(h.ljust(widths[h]) for h in headers))
    print("-+-".join("-" * widths[h] for h in headers))
    for r in rows:
        print(" | ".join(str(r.get(h, "")).ljust(widths[h]) for h in headers))


if __name__ == "__main__":
    main()
