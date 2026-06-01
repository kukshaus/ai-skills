#!/usr/bin/env python3
"""List or perform issue transitions by name (no hard-coded transition IDs)."""
from __future__ import annotations

import argparse
import json
import sys

from jira_client import Jira, md_to_adf, resolve_auth, resolve_field_id


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--base-url"); p.add_argument("--email"); p.add_argument("--token")
    p.add_argument("--pat"); p.add_argument("--oauth")
    p.add_argument("key")
    p.add_argument("--list", action="store_true")
    p.add_argument("--to", help="target status name (case-insensitive)")
    p.add_argument("--comment")
    p.add_argument("--field", action="append", default=[],
                   help='"Resolution=Fixed"')
    args = p.parse_args()

    auth = resolve_auth(args)
    j = Jira(auth)

    transitions = j.get(f"issue/{args.key}/transitions",
                        params={"expand": "transitions.fields"})["transitions"]
    if args.list or not args.to:
        for t in transitions:
            req = ", ".join(
                f"{n}{'(required)' if v.get('required') else ''}"
                for n, v in (t.get("fields") or {}).items()
            )
            print(f"{t['id']:>4}  →  {t['to']['name']:<20}  [{t['name']}]  {req}")
        return

    target = next((t for t in transitions if t["to"]["name"].lower() == args.to.lower()), None)
    if not target:
        sys.exit(f"No transition leads to '{args.to}'. Available: " +
                 ", ".join(t["to"]["name"] for t in transitions))

    body: dict = {"transition": {"id": target["id"]}}
    fields = {}
    for spec in args.field:
        if "=" not in spec:
            sys.exit(f"bad --field '{spec}'")
        name, value = spec.split("=", 1)
        fid = resolve_field_id(j, name.strip())
        v = value.strip()
        fields[fid] = {"name": v} if fid in {"resolution"} else v
    if fields:
        body["fields"] = fields
    if args.comment:
        body["update"] = {"comment": [{"add": {"body": md_to_adf(args.comment)}}]}

    j.post(f"issue/{args.key}/transitions", json_body=body)
    print(json.dumps({"key": args.key, "to": args.to, "ok": True,
                      "url": f"{auth.base_url}/browse/{args.key}"}))


if __name__ == "__main__":
    main()
