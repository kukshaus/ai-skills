# ai-skills

Portable AI skills — one `SKILL.md` per capability, usable by Claude, GitHub Copilot, Cursor, Codex, and any other AGENTS.md-aware assistant.

## Available skills

| Skill | What it does |
|---|---|
| **[jira](skills/jira/)** | Full Atlassian Jira coverage: create / update / transition / link issues, JQL search & saved filters, sprints & boards, attachments, ADF comments, bulk ops, plus premium features (Advanced Roadmaps / Plans, Assets / AQL, Atlas, Rovo, Automation). |

PRDs for each skill live in [`docs/`](docs/).

## How each tool picks up the skill

### Anthropic Claude (Claude.ai Skills / Projects, Claude Code)

Upload the skill folder, or for Claude Code symlink it:

```bash
mkdir -p ~/.claude/skills
ln -s "$PWD/skills/jira" ~/.claude/skills/jira
```

Claude reads the YAML frontmatter (`name`, `description`) and surfaces the skill when the description matches.

### Cursor

```bash
mkdir -p ~/.cursor/skills
ln -s "$PWD/skills/jira" ~/.cursor/skills/jira
```

Or, for a project-scoped skill, put `.cursor/skills/jira/` inside the target repo.

### GitHub Copilot Chat / Codex / any AGENTS.md-aware agent

This repo's [`AGENTS.md`](AGENTS.md) at the root is the index. Open the repo in your editor — Copilot / Codex will read `AGENTS.md` and follow it to `skills/jira/SKILL.md`.

For Copilot custom instructions, also link to `skills/jira/SKILL.md` from `.github/copilot-instructions.md` if your org uses one.

### Generic / Custom GPTs / other agents

Paste the contents of `skills/jira/SKILL.md` into the system prompt, and host the supporting docs (`reference.md`, `jql-cookbook.md`, `premium-features.md`) so the agent can fetch them when needed.

## One-time setup for the Jira skill

```bash
cd skills/jira
pip install -r scripts/requirements.txt
cp .env.example .env             # then fill in JIRA_BASE_URL + auth
python scripts/jira_client.py doctor
```

The doctor probes auth, caches the field map per site, and prints what's missing if anything.

### Auth options (in order of preference)

1. `JIRA_EMAIL` + `JIRA_API_TOKEN` (Jira Cloud)
2. `JIRA_OAUTH_TOKEN` (OAuth 2.0 / 3LO)
3. `JIRA_PAT` (Data Center / Server)
4. OS keychain — `keyring set jira <base-url>`
5. **Browser-session fallback** — if you're already logged in to Jira in Chrome / Edge / Brave / Firefox / Safari, the scripts will reuse that session via `browser_cookie3`.

## Smoke checklist for cross-tool portability

After installing into a tool, verify:

- [ ] The agent surfaces the Jira skill when you mention an issue key like `PROJ-123`.
- [ ] `python skills/jira/scripts/jira_client.py doctor` succeeds.
- [ ] Asking "create a bug in PROJ titled X" results in the agent calling `create_issue.py`, not writing fresh curl.
- [ ] A JQL search ("list my open tickets") uses `search_jql.py` with `--fields` set.
- [ ] A bulk request shows a dry-run **before** changing anything.

## Repo layout

```
ai-skills/
├── AGENTS.md
├── README.md
├── docs/
│   └── PRD-jira-skill.md
└── skills/
    └── jira/
        ├── SKILL.md
        ├── reference.md
        ├── jql-cookbook.md
        ├── premium-features.md
        ├── .env.example
        └── scripts/
            ├── jira_client.py
            ├── jira.sh
            ├── create_issue.py
            ├── search_jql.py
            ├── transition.py
            ├── bulk_update.py
            ├── assets_aql.py
            ├── plans.py
            ├── browser_session.py
            └── requirements.txt
```

## Contributing a new skill

1. Add a folder under `skills/<name>/` with at least a `SKILL.md` (YAML frontmatter: `name`, `description`).
2. Add a PRD under `docs/PRD-<name>-skill.md`.
3. Register the skill in the table at the top of `AGENTS.md`.
4. Keep `SKILL.md` under ~500 lines; push detail to sibling `.md` files.
