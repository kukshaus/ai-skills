# AGENTS.md — instructions for AI coding assistants

This repo hosts portable AI **skills** — markdown contracts that any agent can follow.

## Active skills

| Skill | Use when | Entry point |
|---|---|---|
| **jira** | The user mentions Jira, an issue key like `ABC-123`, JQL, a project, sprint, board, epic, roadmap, Assets/CMDB, Atlas, Rovo, automation rules, or asks to create / find / change a ticket. | [`skills/jira/SKILL.md`](skills/jira/SKILL.md) |

When a skill's "use when" matches the user's request, **read its `SKILL.md` first** before doing anything else. Treat its instructions as authoritative for that domain.

## Conventions for all skills in this repo

- Skill folders are self-contained: `SKILL.md` + reference docs + `scripts/` + `.env.example`.
- Scripts read configuration from environment variables — never from hard-coded paths or commit-checked secrets.
- Prefer executing the provided scripts over generating fresh REST / SDK code.
- Any destructive operation must offer a dry-run and require explicit confirmation.

## Tool-specific notes

- **GitHub Copilot Chat / Codex / generic AGENTS.md consumers**: this file is your index. Open `skills/<name>/SKILL.md` on demand.
- **Anthropic Claude (Skills/Projects, Claude Code)**: upload or symlink `skills/<name>/` — frontmatter (`name`, `description`) makes it discoverable.
- **Cursor**: symlink `skills/<name>/` to `~/.cursor/skills/<name>/` or place under `.cursor/skills/<name>/`.

See [`README.md`](README.md) for one-line install commands per tool.
