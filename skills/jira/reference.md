# Jira Reference

Deep-dive reference. Read sections as needed; you do not need the whole file.

## 1. Base URLs & API versions

| Product | Base URL | Version |
|---|---|---|
| Jira Cloud — Platform | `https://<site>.atlassian.net/rest/api/3/` | **v3 preferred** (v2 still works, ADF differs) |
| Jira Cloud — Agile (boards/sprints) | `https://<site>.atlassian.net/rest/agile/1.0/` | 1.0 |
| Jira Cloud — Service Management | `https://<site>.atlassian.net/rest/servicedeskapi/` | — |
| Jira Cloud — Assets (CMDB) | `https://api.atlassian.com/jsm/assets/workspace/<workspaceId>/v1/` | v1 |
| Data Center / Server | `https://<host>/rest/api/2/` | v2 (no v3 on DC) |

For OAuth 2.0, the host changes to `https://api.atlassian.com/ex/jira/<cloudId>/rest/api/3/`.

## 2. Authentication

### 2.1 Cloud Basic (API token + email)

```
Authorization: Basic base64(<email>:<api_token>)
```

Generate token at `https://id.atlassian.com/manage-profile/security/api-tokens`. Env vars:

```bash
export JIRA_BASE_URL="https://your-site.atlassian.net"
export JIRA_EMAIL="you@company.com"
export JIRA_API_TOKEN="…"
```

### 2.2 OAuth 2.0 (3LO)

For apps acting on behalf of users.

```
Authorization: Bearer <access_token>
```

Scopes for full coverage:
`read:jira-work write:jira-work read:jira-user manage:jira-project manage:jira-configuration read:servicedesk-request manage:servicedesk-customer read:assets write:assets`

Token endpoint: `https://auth.atlassian.com/oauth/token`. Discover Cloud ID via `https://api.atlassian.com/oauth/token/accessible-resources`.

### 2.3 Personal Access Token (Data Center / Server)

```
Authorization: Bearer <pat>
```

Generated in user profile → "Personal Access Tokens". Env: `JIRA_PAT`.

### 2.4 Browser-session fallback

When nothing else is configured but the user is logged in to Jira in their browser:

1. `scripts/browser_session.py` reads cookies from Chrome / Edge / Brave / Vivaldi / Arc / Firefox / Safari for the host of `JIRA_BASE_URL`.
2. The relevant cookies for Cloud are `cloud.session.token`, `atlassian.xsrf.token`, `tenant.session.token`.
3. Requests are sent with the cookie jar and the `Atlassian-Token: no-check` header (for state-changing calls that would otherwise hit XSRF).
4. If MFA / SSO requires a fresh prompt, the agent must tell the user to open Jira in the browser once, then retry — no headless login.

### 2.5 Required headers (write requests)

```
Content-Type: application/json
Accept: application/json
X-Atlassian-Token: no-check         # only needed for some legacy endpoints
```

## 3. Issue CRUD (REST v3)

### 3.1 Create

`POST /rest/api/3/issue`

```json
{
  "fields": {
    "project":     { "key": "PROJ" },
    "issuetype":   { "name": "Bug" },
    "summary":     "Login fails on Safari 17",
    "description": { "type": "doc", "version": 1, "content": [ /* ADF */ ] },
    "priority":    { "name": "High" },
    "labels":      ["safari","sso"],
    "assignee":    { "accountId": "5b10ac8d82e05b22cc7d4ef5" },
    "parent":      { "key": "PROJ-456" },
    "customfield_10016": 5
  }
}
```

- `description` (and any rich text custom field) MUST be ADF on v3.
- `assignee` uses `accountId` on Cloud (not `name` / `username`).
- `parent` replaces the old "Epic Link" custom field.

### 3.2 Read

```
GET /rest/api/3/issue/{issueIdOrKey}?fields=summary,status,assignee&expand=renderedFields,changelog
```

### 3.3 Update

`PUT /rest/api/3/issue/{key}` — same shape as create. Use `update` operations for arrays:

```json
{ "update": { "labels": [ { "add": "needs-qa" }, { "remove": "wip" } ] } }
```

### 3.4 Delete

`DELETE /rest/api/3/issue/{key}?deleteSubtasks=true` — require explicit confirmation.

### 3.5 Field discovery

| Endpoint | Use |
|---|---|
| `GET /rest/api/3/field` | All fields (system + custom) with IDs and clauseNames. |
| `GET /rest/api/3/issue/createmeta/{projectKey}/issuetypes/{issueTypeId}` | Fields available on create, with allowed values. |
| `GET /rest/api/3/issue/{key}/editmeta` | Fields editable for a specific issue. |

Cache these per site to avoid burning tokens on every call.

## 4. Search

### 4.1 New `/search/jql` (use this)

```
POST /rest/api/3/search/jql
{
  "jql": "project = PROJ AND status != Done ORDER BY updated DESC",
  "fields": ["summary","status","assignee"],
  "nextPageToken": null,
  "maxResults": 100
}
```

Response includes `nextPageToken`; keep paging until it's absent. **Total count is NOT returned** by this endpoint — use `POST /rest/api/3/search/approximate-count` for an approximate total.

### 4.2 Legacy `/search` (still works, deprecated)

```
GET /rest/api/3/search?jql=…&fields=…&startAt=0&maxResults=100
```

Returns `total`. Migrate away — it's being phased out.

### 4.3 Saved filters

| Endpoint | Use |
|---|---|
| `GET /rest/api/3/filter/{id}` | Get filter incl. its JQL. |
| `POST /rest/api/3/filter` | Create. Body: `{ "name", "jql", "description", "favourite": true }`. |
| `PUT /rest/api/3/filter/{id}/permission` | Share with project / group / public. |

## 5. Comments, links, attachments, worklogs

| Action | Endpoint |
|---|---|
| Add comment | `POST /rest/api/3/issue/{key}/comment` — body is ADF |
| Edit / delete comment | `PUT` / `DELETE /rest/api/3/issue/{key}/comment/{id}` |
| Link issues | `POST /rest/api/3/issueLink` `{ "type": {"name":"Blocks"}, "inwardIssue":{"key":"A"}, "outwardIssue":{"key":"B"} }` |
| Remote link (e.g. PR) | `POST /rest/api/3/issue/{key}/remotelink` |
| Attach | `POST /rest/api/3/issue/{key}/attachments` — multipart, header `X-Atlassian-Token: no-check` |
| Worklog | `POST /rest/api/3/issue/{key}/worklog` `{ "timeSpent": "1h 30m", "comment": <adf> }` |

## 6. Transitions

```
GET  /rest/api/3/issue/{key}/transitions             # list available transitions for current state
POST /rest/api/3/issue/{key}/transitions
{
  "transition": { "id": "31" },
  "fields":     { "resolution": { "name": "Fixed" } },
  "update":     { "comment": [ { "add": { "body": <adf> } } ] }
}
```

Transition IDs are workflow-specific — always list first.

## 7. Bulk

| Action | Endpoint |
|---|---|
| Bulk create | `POST /rest/api/3/issue/bulk` (up to 50 / call) |
| Bulk fetch | `POST /rest/api/3/issue/bulkfetch` |
| Bulk edit (Cloud, preview) | `POST /rest/api/3/bulk/issues/fields` (returns `taskId` to poll) |
| Bulk transition | `POST /rest/api/3/bulk/issues/transition` |
| Bulk delete | `POST /rest/api/3/bulk/issues/delete` |

Always poll `GET /rest/api/3/task/{taskId}` until status is `COMPLETE` / `FAILED`.

## 8. Agile API

Base: `/rest/agile/1.0/`

| Endpoint | Purpose |
|---|---|
| `GET /board?projectKeyOrId=PROJ` | Boards for a project |
| `GET /board/{id}/sprint?state=active,future,closed` | Sprints on a board |
| `POST /sprint` | Create sprint `{ "originBoardId", "name", "startDate", "endDate", "goal" }` |
| `POST /sprint/{id}/issue` | Move issues into sprint `{ "issues": ["A","B"] }` |
| `POST /sprint/{id}` (state=closed) | Complete sprint |
| `GET /board/{id}/backlog?jql=…` | Backlog |
| `GET /board/{id}/epic` | Epics on board |
| `PUT /issue/{key}/rank` | `{ "rankBeforeIssue" \| "rankAfterIssue" }` |

## 9. ADF (Atlassian Document Format) — minimum viable

A paragraph with bold + a link:

```json
{
  "type": "doc",
  "version": 1,
  "content": [
    {
      "type": "paragraph",
      "content": [
        { "type": "text", "text": "Repro on " },
        { "type": "text", "text": "staging", "marks": [{ "type": "strong" }] },
        { "type": "text", "text": " — see " },
        { "type": "text", "text": "HAR",
          "marks": [{ "type": "link", "attrs": { "href": "https://…/trace.har" } }] }
      ]
    }
  ]
}
```

Top-level node types we use: `paragraph`, `heading` (`attrs.level` 1-6), `bulletList`/`orderedList` with `listItem`, `codeBlock` (`attrs.language`), `blockquote`, `rule`, `mediaSingle`, `table`. `scripts/jira_client.py adf` converts Markdown → ADF.

## 10. Pagination, rate limits, retries

- New `/search/jql`: cursor-based via `nextPageToken`.
- Legacy/most endpoints: `startAt` + `maxResults` (default 50, max 100).
- Rate limits: Cloud uses cost-based limits + `Retry-After`. Treat any `429` or `503` as backoff (scripts do exponential backoff: 1, 2, 4, 8, 16 s, max 5 retries).
- Long bulk operations return a `taskId`; poll `GET /rest/api/3/task/{taskId}` every 2 s up to 5 min.

## 11. Webhooks & Automation

- User-installed webhooks: `POST /rest/api/3/webhook` (max 5 per app, JQL-filtered).
- Automation rules: managed under Project Settings → Automation. Rules that expose an "Incoming Webhook" trigger can be invoked by `POST` to the rule URL with `{ "issues": ["KEY-1"], "data": {…} }`.
- `GET /rest/api/3/automation/rule` (Cloud) — list rules (requires admin scope).

## 12. Useful project / config endpoints

| Endpoint | Use |
|---|---|
| `GET /rest/api/3/project/search` | List projects (paginated). |
| `GET /rest/api/3/project/{key}` | Project details, lead, components. |
| `GET /rest/api/3/issuetype/project?projectId=…` | Issue types for a project. |
| `GET /rest/api/3/priority` | Available priorities. |
| `GET /rest/api/3/resolution` | Available resolutions. |
| `GET /rest/api/3/status` | Status catalog. |
| `GET /rest/api/3/user/search?query=…` | Find user → `accountId`. |
| `GET /rest/api/3/myself` | Current user (good for `doctor`). |

## 13. Error model

```json
{
  "errorMessages": ["…"],
  "errors": { "summary": "is required", "customfield_10016": "must be a number" }
}
```

Handle both arrays and the per-field object. Always print field-level errors back to the user verbatim; they are accurate and actionable.

## 14. Compatibility notes (Data Center / Server)

- Use `/rest/api/2/` — v3 doesn't exist. Description / comment are plain strings, not ADF.
- `accountId` does not exist — use `name` (username).
- `parent` works for sub-tasks; Epic Link is still a custom field (often `customfield_10008` or `customfield_10014` — discover via `/field`).
- Agile API path is the same.

`jira_client.py` detects DC by probing `/rest/api/3/myself` and falls back to v2 + plain strings automatically.
