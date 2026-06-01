#!/usr/bin/env python3
"""Create a Jira issue. Markdown description is converted to ADF."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from jira_client import Jira, md_to_adf, resolve_auth, resolve_field_id


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--base-url"); p.add_argument("--email"); p.add_argument("--token")
    p.add_argument("--pat"); p.add_argument("--oauth")
    p.add_argument("--project", required=True)
    p.add_argument("--issuetype", required=True)
    p.add_argument("--summary", required=True)
    g = p.add_mutually_exclusive_group()
    g.add_argument("--description")
    g.add_argument("--description-file")
    p.add_argument("--priority")
    p.add_argument("--labels", help="comma-separated")
    p.add_argument("--assignee", help='accountId or "currentUser" or "unassigned"')
    p.add_argument("--reporter", help="accountId")
    p.add_argument("--parent", help="parent issue key (epic or parent)")
    p.add_argument("--components", help="comma-separated names")
    p.add_argument("--fix-version", action="append", default=[])
    p.add_argument("--field", action="append", default=[],
                   help='extra fields: "Story Points=5" or "customfield_10016=5"')
    args = p.parse_args()

    auth = resolve_auth(args)
    j = Jira(auth)

    fields: dict = {
        "project":   {"key": args.project},
        "issuetype": {"name": args.issuetype},
        "summary":   args.summary,
    }
    desc_md = args.description or (Path(args.description_file).read_text() if args.description_file else None)
    if desc_md:
        fields["description"] = md_to_adf(desc_md)
    if args.priority:
        fields["priority"] = {"name": args.priority}
    if args.labels:
        fields["labels"] = [l.strip() for l in args.labels.split(",") if l.strip()]
    if args.components:
        fields["components"] = [{"name": c.strip()} for c in args.components.split(",")]
    if args.fix_version:
        fields["fixVersions"] = [{"name": v} for v in args.fix_version]
    if args.assignee:
        if args.assignee == "unassigned":
            fields["assignee"] = None
        elif args.assignee == "currentUser":
            me = j.get("myself")
            fields["assignee"] = {"accountId": me.get("accountId")} if me.get("accountId") else {"name": me.get("name")}
        else:
            fields["assignee"] = {"accountId": args.assignee}
    if args.reporter:
        fields["reporter"] = {"accountId": args.reporter}
    if args.parent:
        fields["parent"] = {"key": args.parent}

    for spec in args.field:
        if "=" not in spec:
            sys.exit(f"bad --field '{spec}'")
        name, value = spec.split("=", 1)
        fid = resolve_field_id(j, name.strip())
        v: object = value.strip()
        if v.startswith("{") or v.startswith("["):
            try: v = json.loads(v)
            except Exception: pass
        elif v.isdigit():
            v = int(v)
        fields[fid] = v

    res = j.post("issue", json_body={"fields": fields})
    key = res["key"]
    print(json.dumps({"key": key, "id": res.get("id"),
                      "url": f"{auth.base_url}/browse/{key}"}, indent=2))


if __name__ == "__main__":
    main()
