#!/usr/bin/env bash
# Thin curl wrapper for ad-hoc Jira REST calls.
# Uses the same auth resolution order as jira_client.py for env vars.
#
# Usage:
#   jira.sh get   issue/PROJ-789
#   jira.sh post  issue                    body.json
#   jira.sh put   issue/PROJ-789           body.json
#   jira.sh del   issue/PROJ-789
#   jira.sh jql   'project = PROJ' summary,status
#
# Reads:
#   JIRA_BASE_URL    (required)
#   JIRA_EMAIL + JIRA_API_TOKEN   (Cloud)
#   JIRA_PAT                       (Data Center / Server)
#   JIRA_OAUTH_TOKEN               (OAuth 2.0)

set -euo pipefail

if [[ -z "${JIRA_BASE_URL:-}" ]]; then
  echo "JIRA_BASE_URL is not set." >&2
  exit 2
fi

auth_args=()
if [[ -n "${JIRA_EMAIL:-}" && -n "${JIRA_API_TOKEN:-}" ]]; then
  auth_args=(-u "$JIRA_EMAIL:$JIRA_API_TOKEN")
elif [[ -n "${JIRA_OAUTH_TOKEN:-}" ]]; then
  auth_args=(-H "Authorization: Bearer $JIRA_OAUTH_TOKEN")
elif [[ -n "${JIRA_PAT:-}" ]]; then
  auth_args=(-H "Authorization: Bearer $JIRA_PAT")
else
  echo "No Jira credentials. Set JIRA_EMAIL+JIRA_API_TOKEN, JIRA_OAUTH_TOKEN, or JIRA_PAT." >&2
  echo "Or use jira_client.py which can fall back to the browser session." >&2
  exit 2
fi

API="$JIRA_BASE_URL/rest/api/3"
common=(-sS --fail-with-body "${auth_args[@]}" \
  -H "Accept: application/json" -H "Content-Type: application/json")

cmd="${1:-}"; shift || true
case "$cmd" in
  get)
    path="$1"; shift
    curl "${common[@]}" "$API/$path" "$@"
    ;;
  post|put|del|delete)
    method="$(echo "$cmd" | tr a-z A-Z)"
    [[ "$method" == "DEL" ]] && method="DELETE"
    path="$1"; shift
    body="${1:-}"
    if [[ -n "$body" && -f "$body" ]]; then
      curl "${common[@]}" -X "$method" "$API/$path" --data-binary "@$body"
    else
      curl "${common[@]}" -X "$method" "$API/$path"
    fi
    ;;
  jql)
    jql="$1"; fields="${2:-summary,status,assignee}"
    body=$(python3 -c "import json,sys; print(json.dumps({'jql':sys.argv[1],'fields':sys.argv[2].split(','),'maxResults':100}))" "$jql" "$fields")
    curl "${common[@]}" -X POST "$API/search/jql" --data-binary "$body"
    ;;
  meta)
    project="$1"; itype="$2"
    curl "${common[@]}" "$API/issue/createmeta/$project/issuetypes" \
      | python3 -c "import json,sys,itertools; d=json.load(sys.stdin); t=next((x for x in d.get('issueTypes',d.get('values',[])) if x['name']==sys.argv[1]),None); print(json.dumps(t or {'error':'issuetype not found','available':[x['name'] for x in d.get('issueTypes',d.get('values',[]))]},indent=2))" "$itype"
    ;;
  *)
    sed -n '2,15p' "$0"
    exit 2
    ;;
esac
