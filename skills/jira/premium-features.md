# Premium & paid features

Coverage map and how to drive each from the agent. Each section starts with the **plan required** so you can degrade gracefully.

| Feature | Plan |
|---|---|
| Advanced Roadmaps / Plans | Jira Software / Cloud **Premium** |
| Assets (CMDB) + AQL | Jira Service Management **Premium** |
| Atlas goals / projects | Free Atlas (works with any Jira) |
| Rovo / Atlassian Intelligence | **Premium** + Rovo add-on (varies by region) |
| Automation rules — unlimited & global | **Premium / Enterprise** (Standard has limits) |
| Sandbox / Release tracks | **Premium / Enterprise** |
| Advanced auditing | **Premium / Enterprise** |

Always check `python scripts/jira_client.py doctor --features` to see what the site is licensed for before attempting these.

---

## 1. Advanced Roadmaps (Plans)

Cross-project planning, scenarios, dependencies, capacity.

### Concepts

- **Plan** — a saved view that pulls issues from one or more **Issue Sources** (projects, boards, filters).
- **Scenario** — what-if changes layered on top of the plan; can be committed back to Jira or discarded.
- **Schedule** — auto-scheduling based on estimates, dependencies, team capacity, releases.

### Endpoints

```
GET  /rest/api/3/plans/plan                      # list plans
GET  /rest/api/3/plans/plan/{planId}             # plan detail incl. issue sources
POST /rest/api/3/plans/plan                      # create plan
PUT  /rest/api/3/plans/plan/{planId}             # update plan
POST /rest/api/3/plans/plan/{planId}/archive
POST /rest/api/3/plans/plan/{planId}/duplicate
GET  /rest/api/3/plans/plan/{planId}/teams       # teams attached to the plan
POST /rest/api/3/plans/plan/{planId}/teams/planning
```

Scenario changes (issues' start/end, parents, sprints) live behind `/scenario` sub-resources — paths change between revisions, so use the helper instead of hard-coding:

```bash
python scripts/plans.py list
python scripts/plans.py show --plan 17
python scripts/plans.py issues --plan 17 --jql 'status != Done'
python scripts/plans.py reschedule --plan 17 --issue PROJ-42 \
    --start 2026-07-01 --due 2026-07-15 --commit            # omit --commit for scenario only
python scripts/plans.py dependencies --plan 17 --of PROJ-42
```

### Common asks

- **"Push Initiative-42 by 2 sprints"** → `plans.py reschedule --issue PROJ-42 --shift-sprints 2 --commit`.
- **"What's the critical path?"** → `plans.py critical-path --plan 17` (computed locally from `/issues` + links of type `blocks`).
- **"Show cross-team dependencies"** → `plans.py dependencies --plan 17 --cross-team`.

---

## 2. Assets (CMDB) + AQL

Asset Query Language is to Assets what JQL is to issues.

### Concepts

- **Workspace** — top-level container, has a unique `workspaceId`.
- **Schema** — e.g. "IT Infrastructure", contains object types.
- **Object type** — e.g. "Server", "Application", "Person".
- **Object** — an instance, e.g. server `web-prod-07`.

### Discover the workspace

```
GET https://api.atlassian.com/jsm/assets/workspace/{workspaceId}/v1/...
```

To find your `workspaceId`:

```
GET https://<site>.atlassian.net/rest/servicedeskapi/assets/workspace
```

### AQL examples

```aql
objectType = "Server" AND "Environment" = "Production"
objectType IN ("Server", "Virtual Machine") AND Owner = currentUser()
"IP Address" LIKE "10.0."
objectType = "Application" AND Status != "Decommissioned"
Created > "now(-7d)"
```

Operators: `=`, `!=`, `<`, `<=`, `>`, `>=`, `LIKE`, `IN`, `NOT IN`, `HAVING`, `STARTSWITH`, `ENDSWITH`, `EXISTS`. References to other objects use `Owner.Email = "x@y.com"` dotted syntax.

### Endpoints

```
POST   /jsm/assets/workspace/{ws}/v1/object/aql?startAt=0&maxResults=100
GET    /jsm/assets/workspace/{ws}/v1/object/{id}
POST   /jsm/assets/workspace/{ws}/v1/object/create
PUT    /jsm/assets/workspace/{ws}/v1/object/{id}
DELETE /jsm/assets/workspace/{ws}/v1/object/{id}
GET    /jsm/assets/workspace/{ws}/v1/objectschema/list
GET    /jsm/assets/workspace/{ws}/v1/objecttype/{id}/attributes
```

### Driving it

```bash
python scripts/assets_aql.py query \
    --workspace auto \
    --aql 'objectType = "Server" AND "Environment" = "Production"' \
    --attrs "Name,IP Address,Owner,Status"

# Attach an Asset object to a Jira issue (custom field of type "Assets object")
python scripts/assets_aql.py attach \
    --issue PROJ-789 \
    --field "Affected CI" \
    --object SRV-104
```

### Common asks

- **"Which prod servers run app X?"** → AQL with `objectType=Server AND "Runs Application".Name = "X"`.
- **"List CIs owned by team Y missing patches"** → join via dotted attr to a Patch object type.
- **"Open an incident for every server with Status = Down"** → AQL → loop → `create_issue.py` with the right CI in the asset field.

---

## 3. Atlas — goals & projects

Atlas is Atlassian's goal/project-status product; it's free even on Standard Jira plans but the integration is most useful at scale.

### Endpoints

Atlas is GraphQL-first:

```
POST https://api.atlassian.com/graphql
Authorization: Bearer <oauth-token>     # OAuth required, basic auth not supported
```

Useful queries (the helper script generates these):

- `townsquareGoals(workspaceUuid)`
- `townsquareProjects(workspaceUuid)`
- Linking a Jira issue to an Atlas goal/project uses the `townsquareLinkJiraIssue` mutation.

### Driving it

```bash
python scripts/jira_client.py atlas-link \
    --issue PROJ-789 \
    --goal-key TOWN-123
```

### Common asks

- **"Which Jira issues feed Goal X?"** → query goal's linked items → display table.
- **"Mark this initiative on-track in Atlas"** → posts an update on the Atlas project, not the Jira issue.

---

## 4. Rovo / Atlassian Intelligence

Rovo exposes AI features (summarize, suggest, ask) inside Atlassian products. Programmatic surfaces depend on what your tenant has enabled.

### Available surfaces

| Surface | How |
|---|---|
| In-issue AI summary | `POST /rest/api/3/issue/{key}/summary` (Cloud, Rovo-enabled tenants). Helper: `jira_client.py rovo-summarize <KEY>`. |
| AI-suggested reply (JSM) | Service Desk panel only — not stable in REST yet. |
| AI work-item creation | Some tenants expose `POST /rest/api/3/ai/issue/draft` (beta). Helper probes for it. |
| Rovo Agents | Custom agents are configured in Admin → Atlassian Intelligence → Rovo Agents. They are invoked from within products, not via public REST. |

### Driving it

```bash
python scripts/jira_client.py rovo-summarize PROJ-789           # adds an AI summary as a comment
python scripts/jira_client.py rovo-draft \
    --project PROJ --issuetype Story \
    --prompt "User can export reports as CSV from the dashboard"
```

If the endpoint returns 404, your tenant doesn't have Rovo enabled — tell the user and stop.

---

## 5. Automation rules

Even Standard tenants get limited automation; Premium removes monthly run limits and unlocks global rules.

### Endpoints (Cloud)

```
GET  /rest/api/3/automation/rule                 # list rules (admin scope)
GET  /rest/api/3/automation/rule/{id}
POST /rest/api/3/automation/rule/{id}/execution  # manually trigger
```

Rules with an **Incoming Webhook** trigger expose a URL like:

```
https://automation.atlassian.com/pro/hooks/<token>
```

Trigger:

```bash
curl -X POST "$WEBHOOK_URL" -H "Content-Type: application/json" \
     -d '{ "issues": ["PROJ-789"], "data": { "reason": "manual replay" } }'
```

### Helper

```bash
python scripts/jira_client.py automation list
python scripts/jira_client.py automation trigger --rule 42 --issue PROJ-789
python scripts/jira_client.py automation trigger --webhook "$WEBHOOK_URL" \
    --issues PROJ-789,PROJ-790 --data '{"reason":"replay"}'
```

### Common asks

- **"Why didn't rule X run on this issue?"** → `automation history --rule 42 --issue PROJ-789` (shows audit log).
- **"Disable the auto-close rule for the weekend"** → `automation toggle --rule 42 --enabled false`.

---

## 6. Service Management (JSM) niceties — adjacent

Not strictly premium, but commonly bundled:

- Request types: `GET /rest/servicedeskapi/servicedesk/{id}/requesttype`.
- Customer requests: `POST /rest/servicedeskapi/request`.
- SLAs: `GET /rest/api/3/issue/{key}?expand=sla` (uses `customfield_*` per SLA).
- Approvals: `GET /rest/api/3/issue/{key}/approval/{id}`.

`jira_client.py servicedesk …` wraps the common flows.

---

## 7. Degrading when premium isn't available

If a script returns 402 / 403 / 404 specifically because the feature is gated:

1. Tell the user what plan is required.
2. Offer the **closest free alternative** — e.g. for Plans, fall back to a JQL query across the projects and a static dependency table; for Rovo summarize, fall back to letting the agent write the summary itself.
3. Never silently retry on a different endpoint hoping it works.
