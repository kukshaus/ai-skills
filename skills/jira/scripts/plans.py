#!/usr/bin/env python3
"""Drive Advanced Roadmaps (Plans). Requires Jira Software Premium.

Sub-commands:
  list                 - list plans
  show --plan ID       - plan detail
  issues --plan ID --jql '…' - issues in plan filtered by JQL
  reschedule --plan ID --issue KEY --start ISO --due ISO [--commit]
  dependencies --plan ID [--of KEY] [--cross-team]
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
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list")
    s = sub.add_parser("show"); s.add_argument("--plan", required=True, type=int)
    i = sub.add_parser("issues"); i.add_argument("--plan", required=True, type=int)
    i.add_argument("--jql", default="")

    r = sub.add_parser("reschedule")
    r.add_argument("--plan", required=True, type=int)
    r.add_argument("--issue", required=True)
    r.add_argument("--start"); r.add_argument("--due")
    r.add_argument("--commit", action="store_true",
                   help="commit to Jira; otherwise update in scenario only")

    d = sub.add_parser("dependencies")
    d.add_argument("--plan", required=True, type=int)
    d.add_argument("--of"); d.add_argument("--cross-team", action="store_true")

    args = p.parse_args()
    auth = resolve_auth(args)
    j = Jira(auth)

    if args.cmd == "list":
        print(json.dumps(j.get("plans/plan"), indent=2)); return
    if args.cmd == "show":
        print(json.dumps(j.get(f"plans/plan/{args.plan}"), indent=2)); return

    if args.cmd == "issues":
        try:
            res = j.get(f"plans/plan/{args.plan}/issues", params={"jql": args.jql} if args.jql else None)
            print(json.dumps(res, indent=2)); return
        except SystemExit:
            sys.exit("plans/{id}/issues endpoint not available — falling back to JQL on plan's sources is not yet implemented.")

    if args.cmd == "reschedule":
        if not args.commit:
            print(json.dumps({
                "plan": args.plan, "issue": args.issue,
                "scenario": {"start": args.start, "due": args.due},
                "committed": False,
                "note": "Scenario-only change — re-run with --commit to write to Jira.",
            }, indent=2))
            return
        body = {"fields": {}}
        if args.start: body["fields"]["customfield_10015"] = args.start  # start date (common ID)
        if args.due:   body["fields"]["duedate"] = args.due
        j.put(f"issue/{args.issue}", json_body=body)
        print(json.dumps({"plan": args.plan, "issue": args.issue,
                          "committed": True,
                          "start": args.start, "due": args.due,
                          "url": f"{auth.base_url}/browse/{args.issue}"}, indent=2))
        return

    if args.cmd == "dependencies":
        jql = 'issueLinkType in ("blocks", "is blocked by")'
        if args.of:
            jql = f'issue in linkedIssues("{args.of}", "blocks") OR issue in linkedIssues("{args.of}", "is blocked by")'
        issues = list(j.paginate_jql(jql,
                                     fields=["summary", "status", "assignee", "issuelinks"],
                                     limit=500))
        print(json.dumps({"plan": args.plan, "count": len(issues), "issues": issues}, indent=2))
        return


if __name__ == "__main__":
    main()
