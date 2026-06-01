# PRD — Jira Agent Skill

| Field | Value |
|---|---|
| Status | Draft v1 |
| Owner | AI Skills repo |
| Target consumers | Anthropic Claude (Skills/Projects), Claude Code, GitHub Copilot Chat, Cursor Agent, OpenAI Codex/Custom GPTs, any AGENTS.md-aware tool |
| Format | Portable `SKILL.md` (YAML frontmatter + Markdown) + `AGENTS.md` shim |

## 1. Problem

Engineers and PMs work with Jira every day (create issues, triage, build JQL filters, manage sprints, plan roadmaps, query Assets/CMDB), but they re-explain the same context to their AI assistant every session: site URL, auth, project keys, custom fields, JQL syntax, REST quirks, premium endpoints. Each assistant (Claude, Copilot, Cursor) has slightly different rules for picking up reusable instructions, so teams end up maintaining N copies.

## 2. Goal

Ship **one** Jira skill that:

1. Is the single source of truth for "how an AI should work with Jira" — from a one-line ticket request to bulk migrations and Advanced Roadmaps planning.
2. Loads natively in Claude Skills, Cursor Skills, and via `AGENTS.md` for Copilot/Codex/other agents — without forking content.
3. Ships executable scripts so the agent stops re-inventing curl/Python every time.
4. Covers Cloud + Data Center + premium (Advanced Roadmaps, Assets/CMDB, Atlas, Rovo / Atlassian Intelligence).
5. Supports four auth modes including reusing the user's **logged-in browser session** when no token is configured.

## 3. Non-goals

- Replacing the Jira UI or building a TUI.
- Hosting credentials. Auth material always lives in env vars or the user's keychain/browser.
- Wrapping every Atlassian product (Confluence, Bitbucket, Compass) — those get sibling skills later.
- Locking to a single agent runtime — no Cursor-only or Claude-only features.

## 4. Target users & top jobs-to-be-done

| Persona | JTBD |
|---|---|
| Developer | "Create a bug from this stack trace, link it to the epic, set sprint." |
| Tech lead | "Show me all unresolved P1s across our 3 projects, group by assignee." |
| PM | "Build a JQL filter for the QBR review and save it." |
| SRE / Service desk | "Find the CI in Assets, attach it to this incident, update the customer." |
| Program manager | "Re-plan the roadmap — push Initiative-42 by 2 sprints in Advanced Roadmaps." |
| Anyone | "What changed on PROJ-1234 in the last 24h?" |

## 5. Scope

### 5.1 In scope (v1)

**Issues & workflow**
- Create / read / update / transition / delete issues (REST API v3)
- Comments (incl. ADF — Atlassian Document Format), worklogs, attachments
- Links, sub-tasks, parent/child (incl. Epic Link / `parent` field)
- Custom fields — discovery via `/field` + `editmeta`
- Bulk operations (`/bulk`) and batched create

**Search & filter**
- JQL cookbook: project, status, assignee, labels, sprint, date ranges, history, EXISTS, WAS, CHANGED, ORDER BY
- Saved filters: create, share, subscribe
- Pagination (`nextPageToken` for the new `/search/jql` v3 endpoint)
- Advanced JQL functions (`linkedIssues()`, `membersOf()`, `issueHistory()`, `endOfWeek()` …)

**Agile**
- Boards, sprints (start/complete/move issues), backlog, velocity
- Epics, scrum vs kanban specifics
- Agile REST `/rest/agile/1.0/`

**Premium / paid features**
- **Advanced Roadmaps (Plans)**: list plans, scenarios, schedule, cross-project dependencies
- **Assets / CMDB** (Jira Service Management Premium): AQL queries, object schemas, attaching objects to issues
- **Atlas** (Atlassian goals/projects): linking Jira issues to Atlas goals & projects
- **Rovo / Atlassian Intelligence**: summarize issue, suggest reply, AI work items (where exposed via API/MCP)
- **Automation rules**: read rule library, trigger via webhook
- **Insights / advanced reporting** endpoints

**Auth modes (all four)**
1. Jira Cloud API token + email (Basic)
2. OAuth 2.0 3LO (for apps acting on behalf of a user)
3. Personal Access Token (Data Center / Server)
4. **Browser-session fallback**: reuse the user's existing logged-in Atlassian session via cookie jar (`cloud.session.token`, `atlassian.xsrf.token`) when no token is set — read from the OS keychain / browser profile.

**Integration paths**
- Direct REST (curl + python `requests`)
- Atlassian Remote MCP server (when available in the host)
- `gh`-style CLI fallback via `acli` / `jira-cli` if installed

### 5.2 Out of scope (v1)

- Confluence, Bitbucket, Compass, Statuspage, Opsgenie (separate future skills).
- Writing Forge apps / Connect apps from scratch (only invoking them).
- Migrating from Server to Cloud.

## 6. Requirements

### 6.1 Functional

| # | Requirement |
|---|---|
| F1 | Agent can create an issue from a free-text description, inferring project, issuetype, priority, labels. |
| F2 | Agent can build, validate, and execute JQL — paginating safely. |
| F3 | Agent can transition an issue through any workflow without hard-coding transition IDs (looks them up). |
| F4 | Agent handles ADF for any field that requires it (description, comments, environment). |
| F5 | Agent can attach files and read attachments. |
| F6 | Agent can perform bulk updates with dry-run preview. |
| F7 | Agent can query Advanced Roadmaps Plans and modify scenarios. |
| F8 | Agent can run AQL against Assets and link objects to issues. |
| F9 | Agent picks the right auth automatically: env vars → keychain → browser session, in that order. |
| F10 | Agent surfaces a clear, actionable error when auth, permission, or schema mismatches occur. |

### 6.2 Non-functional

- **Portability**: SKILL.md + AGENTS.md is the entire contract. No Cursor-specific or Claude-specific tags inside the body.
- **Token efficiency**: SKILL.md ≤ 500 lines; deep detail lives in `reference.md`, `jql-cookbook.md`, `premium-features.md`.
- **Safety**: any destructive op (delete issue, bulk transition, complete sprint) must show a dry-run / confirmation step.
- **Determinism**: scripts return JSON to stdout, errors to stderr, non-zero exit codes on failure.
- **No secrets in repo**: scripts read `JIRA_BASE_URL`, `JIRA_EMAIL`, `JIRA_API_TOKEN`, `JIRA_PAT`, `JIRA_OAUTH_TOKEN` from env.

## 7. Solution overview

```
ai-skills/
├── docs/
│   └── PRD-jira-skill.md
├── skills/
│   └── jira/
│       ├── SKILL.md              # Entrypoint — agent reads this first
│       ├── reference.md          # REST v3 + Agile + auth deep dive
│       ├── jql-cookbook.md       # Search & filter recipes
│       ├── premium-features.md   # Plans, Assets, Atlas, Rovo
│       └── scripts/
│           ├── jira_client.py    # Auth + request wrapper (the one importable lib)
│           ├── jira.sh           # Curl-based wrapper for shell workflows
│           ├── create_issue.py
│           ├── search_jql.py
│           ├── transition.py
│           ├── bulk_update.py
│           ├── assets_aql.py
│           ├── plans.py
│           └── browser_session.py # Falls back to logged-in browser cookies
├── AGENTS.md                     # Makes Copilot/Codex/etc. discover the skill
└── README.md                     # Install/usage for each AI tool
```

### 7.1 Portability strategy

| Tool | How it loads the skill |
|---|---|
| Anthropic Claude (Skills/Projects) | Upload `skills/jira/` folder; Claude reads `SKILL.md` frontmatter. |
| Claude Code | Symlink to `~/.claude/skills/jira/` or add via `claude skills add`. |
| Cursor Agent | Symlink to `~/.cursor/skills/jira/` or place in `.cursor/skills/jira/`. |
| GitHub Copilot Chat / Codex | Reads `AGENTS.md` at repo root — it points at `skills/jira/SKILL.md`. |
| Generic / Custom GPT | Same — point the system prompt at `skills/jira/SKILL.md`. |

`SKILL.md` uses only the lowest-common-denominator frontmatter (`name`, `description`) — no Cursor-only `disable-model-invocation` etc. in the body.

### 7.2 Auth resolution order

```
1. Explicit args to script (--token / --email)
2. Env: JIRA_API_TOKEN + JIRA_EMAIL  (Cloud Basic)
3. Env: JIRA_OAUTH_TOKEN              (OAuth 2.0 3LO)
4. Env: JIRA_PAT                      (Data Center / Server)
5. OS keychain entry (service="jira", account=JIRA_BASE_URL)
6. Browser session  (scripts/browser_session.py reads Chrome/Firefox/Safari cookies for the JIRA_BASE_URL host)
7. Fail with actionable message listing the 6 options.
```

## 8. Success metrics

- A user can go from "fresh repo + Jira account" to creating an issue via the agent in **< 2 min**.
- ≥ 90 % of common asks (create / search / transition / comment / link / bulk) handled **without** the agent writing fresh REST code — it calls the provided scripts.
- Same skill folder works unchanged on Claude, Cursor, and Copilot (verified by smoke checklist in README).
- Zero credentials committed (verified by repo secret-scanning).

## 9. Risks & mitigations

| Risk | Mitigation |
|---|---|
| Atlassian deprecates `/search` in favour of `/search/jql` (already happening). | Scripts use `/search/jql` with `nextPageToken`; `reference.md` documents both. |
| Browser-session auth breaks on Atlassian SSO / MFA. | Treat as best-effort fallback; print a clear "log in once in your browser, then retry" message. |
| Custom fields differ per tenant. | Discovery script `jira_client.py fields` caches a per-site field map in `~/.cache/jira-skill/`. |
| Premium endpoints vary by plan. | `premium-features.md` clearly marks Standard vs Premium vs Enterprise and degrades gracefully. |
| Token sprawl across AI tools. | Single env-var contract; README shows how to source one `.env` everywhere. |

## 10. Milestones

| M | Deliverable |
|---|---|
| M1 | Skeleton: `SKILL.md` + `reference.md` + `jira_client.py` + 4 core scripts (create/search/transition/comment). |
| M2 | JQL cookbook + bulk + attachments + browser-session auth. |
| M3 | Premium: Plans, Assets/AQL, Atlas links, Rovo summarize. |
| M4 | AGENTS.md polish + README install matrix + smoke checklist. |

v1 of this repo ships M1–M4 together.

## 11. Open questions

1. Should the skill also ship a tiny MCP server stub for hosts that prefer MCP over scripts? (Probably v2.)
2. Auto-detect Forge custom apps and document their endpoints? (v2.)
3. Bundle a `.env.example` at repo root or only inside `skills/jira/`? **Decision:** inside the skill folder, to keep skills self-contained.
