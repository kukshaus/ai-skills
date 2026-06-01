#!/usr/bin/env python3
"""Query Atlassian Assets (CMDB) with AQL, or attach an Asset object to a Jira issue.

Requires JSM Premium. Auth: same as jira_client (OAuth 2.0 strongly recommended;
Basic + API token also works on Cloud).
"""
from __future__ import annotations

import argparse
import json
import sys

from jira_client import Jira, resolve_auth


def _resolve_workspace(j: Jira) -> str:
    res = j.get(f"{j.auth.base_url}/rest/servicedeskapi/assets/workspace")
    values = res.get("values") or []
    if not values:
        sys.exit("No Assets workspace on this site (JSM Premium required).")
    return values[0]["workspaceId"]


def _asset_url(ws: str, suffix: str) -> str:
    return f"https://api.atlassian.com/jsm/assets/workspace/{ws}/v1/{suffix.lstrip('/')}"


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--base-url"); p.add_argument("--email"); p.add_argument("--token")
    p.add_argument("--pat"); p.add_argument("--oauth")
    sub = p.add_subparsers(dest="cmd", required=True)

    q = sub.add_parser("query")
    q.add_argument("--workspace", default="auto")
    q.add_argument("--aql", required=True)
    q.add_argument("--attrs", default="", help="comma-separated attribute names to include")
    q.add_argument("--limit", type=int, default=100)

    a = sub.add_parser("attach")
    a.add_argument("--issue", required=True)
    a.add_argument("--field", required=True, help="custom field name or ID of type 'Assets object'")
    a.add_argument("--object", required=True, help="Asset object key, e.g. SRV-104")

    args = p.parse_args()
    auth = resolve_auth(args)
    j = Jira(auth)

    if args.cmd == "query":
        ws = args.workspace if args.workspace != "auto" else _resolve_workspace(j)
        results = []
        start = 0
        while True:
            res = j.post(_asset_url(ws, "object/aql"),
                         params={"startAt": start, "maxResults": 100},
                         json_body={"qlQuery": args.aql})
            objs = res.get("values") or res.get("objects") or []
            for o in objs:
                row = {"id": o.get("id"), "key": o.get("objectKey"), "name": o.get("label")}
                if args.attrs:
                    by = {a["objectTypeAttribute"]["name"]: a for a in (o.get("attributes") or [])}
                    for name in [n.strip() for n in args.attrs.split(",") if n.strip()]:
                        v = by.get(name)
                        if v:
                            vals = [x.get("displayValue") for x in v.get("objectAttributeValues", [])]
                            row[name] = vals[0] if len(vals) == 1 else vals
                results.append(row)
                if args.limit and len(results) >= args.limit:
                    break
            if args.limit and len(results) >= args.limit: break
            if not res.get("isLast", True) and objs:
                start += len(objs); continue
            break
        print(json.dumps({"aql": args.aql, "count": len(results), "objects": results}, indent=2))
        return

    if args.cmd == "attach":
        from jira_client import resolve_field_id
        fid = resolve_field_id(j, args.field)
        ws = _resolve_workspace(j)
        obj = j.get(_asset_url(ws, f"object/{args.object}"))
        oid = obj.get("id")
        j.put(f"issue/{args.issue}", json_body={
            "fields": {fid: [{"workspaceId": ws, "id": str(oid), "objectId": str(oid)}]}
        })
        print(json.dumps({"issue": args.issue, "field": args.field,
                          "object": args.object, "ok": True}))


if __name__ == "__main__":
    main()
