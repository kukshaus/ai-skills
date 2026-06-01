---
name: jira
description: >-
  Work with Atlassian Jira end-to-end: create / update / transition / link
  issues, build and run JQL searches and filters, manage sprints, boards and
  backlogs, handle attachments, comments (ADF) and bulk operations, and drive
  premium features (Advanced Roadmaps / Plans, Assets & AQL, Atlas goals,
  Rovo / Atlassian Intelligence, automation rules). Use whenever the user
  mentions Jira, an issue key like ABC-123, JQL, a Jira project, sprint,
  board, epic, roadmap, Assets / CMDB, Atlas, Atlassian, Rovo, or asks to
  create / find / change a ticket.
---

# Jira Skill

This skill is your contract for any Jira work. Read this file first. Open the linked references only when the task needs them.

- [`reference.md`](reference.md) — REST API v3 + Agile API + ADF + auth deep dive
- [`jql-cookbook.md`](jql-cookbook.md) — search & filter recipes
- [`premium-features.md`](premium-features.md) — Advanced Roadmaps, Assets/AQL, Atlas, Rovo, Automation

## 1. Operating principles

1. **Prefer the provided scripts in `scripts/`** over writing fresh `curl`/`requests` code. They handle auth, pagination, ADF, retries, and error formatting.
2. **Never invent issue keys, project keys, custom field IDs, or transition IDs.** Look them up first (`jira.sh meta`, `jira_client.py fields`, `transition.py --list`).
3. **Be conservative with destructive actions.** Delete, bulk-update, sprint-complete, and workflow-bypass operations require a dry-run preview that the user confirms.
4. **Always paginate** — never assume a single page returns everything. Use `nextPageToken` (new `/search/jql`) or `startAt`/`maxResults` (legacy).
5. **Respect ADF.** `description`, `comment.body`, `environment`, and custom rich-text fields require Atlassian Document Format on REST v3, not plain strings.
6. **Surface the issue URL** (`$JIRA_BASE_URL/browse/<KEY>`) whenever you reference an issue, so the user can click through.

## 2. First-run setup (do this once)

Run the doctor to detect site, auth mode, and project cache:

```bash
python scripts/jira_client.py doctor
```

It will:
1. Resolve `JIRA_BASE_URL` (env → keychain → browser cookies).
2. Pick the first working auth from the order below.
3. Cache the field map, project keys, and issue types to `~/.cache/jira-skill/<site>.json`.

### Auth resolution order

| # | Source | Env vars / location |
|---|---|---|
| 1 | Explicit CLI flags | `--token`, `--email`, `--pat`, `--oauth` |
| 2 | Jira Cloud Basic | `JIRA_BASE_URL`, `JIRA_EMAIL`, `JIRA_API_TOKEN` |
| 3 | OAuth 2.0 (3LO) | `JIRA_OAUTH_TOKEN` (+ `JIRA_CLOUD_ID` if known) |
| 4 | Data Center / Server PAT | `JIRA_BASE_URL`, `JIRA_PAT` |
| 5 | OS keychain | service `jira`, account = `JIRA_BASE_URL` |
| 6 | **Browser session** | `python scripts/browser_session.py` reads cookies from Chrome/Edge/Brave/Firefox/Safari for `*.atlassian.net` and reuses them. Use when nothing else is configured but the user is logged in to Jira in their browser. |

If none works, the doctor prints exactly what to set. **Never** ask the user for a token in chat — instruct them to set the env var or run `keyring set jira <url>`.

## 3. Decision tree — pick the right action

```
User asks about Jira
│
├─ Wants to FIND issues       → §4 Search
├─ Wants to CREATE an issue   → §5 Create
├─ Wants to UPDATE / comment  → §6 Update
├─ Wants to MOVE in workflow  → §7 Transition
├─ Bulk / many issues at once → §8 Bulk
├─ Sprint / board / backlog   → §9 Agile
├─ Roadmap, Plan, scenario    → premium-features.md → Plans
├─ Assets / CMDB / AQL        → premium-features.md → Assets
├─ Atlas goal / project link  → premium-features.md → Atlas
├─ Summarize / AI suggestion  → premium-features.md → Rovo
└─ Unclear                    → ask exactly one clarifying question, then act
```

## 4. Search & filter (JQL)

For anything starting with "find", "show", "list", "how many", "which":

```bash
python scripts/search_jql.py \
  --jql 'project = PROJ AND status != Done AND assignee = currentUser() ORDER BY updated DESC' \
  --fields summary,status,assignee,priority,updated \
  --limit 200
```

- Uses the new `/rest/api/3/search/jql` endpoint with `nextPageToken` pagination.
- Always pass `--fields` — never fetch `*all` unless explicitly asked.
- For saved filters: `python scripts/search_jql.py --filter 12345`.

Building JQL? Open [`jql-cookbook.md`](jql-cookbook.md). Quick reminders:

| Need | Snippet |
|---|---|
| My open work | `assignee = currentUser() AND resolution = Unresolved` |
| In active sprint | `sprint in openSprints()` |
| Stale | `updated < -14d AND status != Done` |
| Changed status today | `status CHANGED DURING (startOfDay(), now())` |
| Linked to an issue | `issue in linkedIssues("PROJ-123")` |
| In an epic | `parent = PROJ-456`  *(replaces deprecated "Epic Link")* |
| By label, any of | `labels in (security, urgent)` |
| Has attachments | `attachments is not EMPTY` |

Validate JQL before running large queries: `python scripts/search_jql.py --validate --jql '…'`.

## 5. Create an issue

Always discover the schema for the target project first (cached):

```bash
python scripts/jira_client.py meta --project PROJ --issuetype Bug
```

Then create. The script accepts plain Markdown for `--description` and converts it to ADF:

```bash
python scripts/create_issue.py \
  --project PROJ \
  --issuetype Bug \
  --summary "Login fails on Safari 17 with SSO" \
  --description-file ./body.md \
  --priority High \
  --labels safari,sso,regression \
  --assignee currentUser \
  --parent PROJ-456            # epic / parent
```

Custom fields: pass `--field "Story Points=5"` or `--field "customfield_10016=5"`. The script resolves names → IDs via the cached field map.

After creation it prints `{"key": "PROJ-789", "url": "…/browse/PROJ-789"}`. Always echo the URL back to the user.

## 6. Update, comment, link, attach

```bash
# Edit any fields (Markdown → ADF for rich-text fields)
python scripts/jira_client.py update PROJ-789 \
  --field "summary=Login fails on Safari 17 (SSO)" \
  --field "labels+=needs-qa"             # +=/-= for array fields

# Comment (Markdown supported)
python scripts/jira_client.py comment PROJ-789 --body "Repro on staging, see attached HAR."

# Link two issues
python scripts/jira_client.py link PROJ-789 --type "blocks" --to PROJ-790

# Attach a file
python scripts/jira_client.py attach PROJ-789 ./trace.har
```

## 7. Transition (workflow)

Never hard-code transition IDs. Always list first:

```bash
python scripts/transition.py PROJ-789 --list
# → 11: "To Do" → "In Progress"
#   21: "In Progress" → "In Review"
#   31: → "Done"  (requires resolution)

python scripts/transition.py PROJ-789 --to "In Review" \
  --comment "PR opened: https://…" \
  --field "Resolution=Fixed"   # only if the transition requires it
```

If the destination requires fields you don't have, the script reports them — ask the user.

## 8. Bulk operations

Always dry-run first. The script prints the diff and exits 0; only with `--apply` does it write.

```bash
# Dry-run: re-label everything in the last sprint
python scripts/bulk_update.py \
  --jql 'sprint = closedSprints() AND project = PROJ AND labels = legacy-id-123' \
  --set "labels-=legacy-id-123" \
  --set "labels+=archived-2026q1"

# Apply
python scripts/bulk_update.py --jql '…' --set '…' --apply
```

Hard limits enforced by the script: max 500 issues per run, max 5 concurrent requests, automatic 429 backoff.

## 9. Agile — sprints, boards, backlog

```bash
# Boards in a project
python scripts/jira_client.py boards --project PROJ

# Sprints on a board
python scripts/jira_client.py sprints --board 42 --state active,future

# Move issues into a sprint
python scripts/jira_client.py sprint-move --sprint 1337 PROJ-1 PROJ-2 PROJ-3

# Start / complete a sprint (complete requires confirmation)
python scripts/jira_client.py sprint-start    --sprint 1337 --start "2026-06-03T08:00:00Z" --end "2026-06-17T17:00:00Z"
python scripts/jira_client.py sprint-complete --sprint 1336 --confirm
```

Kanban: use `--rank-before` / `--rank-after` for ranking instead of sprints.

## 10. Premium features

Open [`premium-features.md`](premium-features.md). Quick map:

| Capability | Plan required | Script |
|---|---|---|
| **Advanced Roadmaps / Plans** — cross-project planning, scenarios, dependencies | Premium | `plans.py` |
| **Assets / CMDB** — AQL queries, object schemas, attach objects to issues | JSM Premium | `assets_aql.py` |
| **Atlas** — link Jira issues to Atlas goals & projects | Standard+ (Atlas free) | `jira_client.py atlas-link` |
| **Rovo / Atlassian Intelligence** — summarize issue, suggest reply, AI work items | Premium / Rovo add-on | `jira_client.py rovo-summarize` |
| **Automation rules** — list rules, trigger via webhook | Standard (limits scale w/ plan) | `jira_client.py automation` |

## 11. Output conventions

When you respond to the user about a Jira action:

- Lead with the **result** (issue key + URL, count of issues changed, etc.).
- Include a compact table for multi-item responses (key, summary, status, assignee).
- Never paste the raw JSON unless the user asks for it.
- For destructive or bulk actions, show the dry-run diff and **stop** until the user confirms.

## 12. Common failure modes — handle these explicitly

| Symptom | Likely cause | Fix |
|---|---|---|
| `401 Unauthorized` | Token expired / wrong email | Re-run `jira_client.py doctor`. |
| `403 Forbidden` | Missing project permission | Tell the user which permission scheme is needed; don't retry. |
| `400` on description/comment | Sent plain string instead of ADF | Use the scripts, or `jira_client.py adf "$markdown"`. |
| `Field 'customfield_xxx' cannot be set` | Field not on screen for that issuetype | Either change issuetype or ask admin to add to screen. |
| Empty results from JQL that "should" match | Field is text-searched, needs `~` not `=` | Use `summary ~ "foo"` / `text ~ "foo"`. |
| Pagination stops early | Using deprecated `/search` without `nextPageToken` | Use `/search/jql` (default in scripts). |
| Browser-session auth fails after MFA | SSO session not exported by browser | Print: "Open Jira once in your default browser, accept any prompts, then retry." |

## 13. Safety rules

- Never commit `JIRA_API_TOKEN`, `JIRA_PAT`, `JIRA_OAUTH_TOKEN`, browser cookies, or `.env` files.
- Never log full tokens — scripts mask everything except the last 4 chars.
- Never bulk-transition issues across projects in one call without explicit `--apply` confirmation.
- Refuse to delete issues (`DELETE /issue`) unless the user types the issue key in confirmation.

## 14. When to read which reference

- Need the exact REST path, headers, or field schema? → [`reference.md`](reference.md)
- Need a JQL snippet or operator? → [`jql-cookbook.md`](jql-cookbook.md)
- Roadmaps / Plans / Assets / Atlas / Rovo / Automation? → [`premium-features.md`](premium-features.md)
- Anything else: act with the scripts.
