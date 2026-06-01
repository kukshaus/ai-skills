# JQL Cookbook

Recipes you can copy. All examples are valid in Jira Cloud; most also work on DC/Server (notes inline).

## 1. Operators cheat sheet

| Category | Operators |
|---|---|
| Comparison | `=`, `!=`, `>`, `>=`, `<`, `<=` |
| Membership | `IN (a, b)`, `NOT IN (…)` |
| Existence | `IS EMPTY`, `IS NOT EMPTY` |
| Text search | `~` (contains, full-text), `!~` |
| Logical | `AND`, `OR`, `NOT`, parentheses |
| Historical | `WAS`, `WAS NOT`, `WAS IN`, `CHANGED` (+ `BY`, `BEFORE`, `AFTER`, `DURING`, `FROM`, `TO`, `ON`) |
| Ordering | `ORDER BY field ASC|DESC` (multiple fields allowed) |

Text fields require `~`, not `=`. Examples: `summary ~ "login"`, `text ~ "stack trace"`.

## 2. Time functions

| Function | Meaning |
|---|---|
| `now()` | Current timestamp |
| `currentLogin()`, `lastLogin()` | This/previous login |
| `startOfDay()`, `endOfDay()` | Today's bounds (accepts offset, e.g. `startOfDay("-1d")`) |
| `startOfWeek()`, `endOfWeek()` | This week (locale-aware) |
| `startOfMonth()`, `endOfMonth()` | |
| `startOfYear()`, `endOfYear()` | |
| Relative literals | `-1d`, `-2w`, `4h`, `-30m` |

Examples:

```jql
created >= -7d
updated < startOfDay()
resolved >= startOfWeek() AND resolved < endOfWeek()
```

## 3. People functions

```jql
assignee = currentUser()
reporter in (currentUser(), "5b10ac…")        # accountId on Cloud
assignee in membersOf("jira-developers")
assignee = unassigned
```

## 4. Project / hierarchy

```jql
project = PROJ
project in (PROJ, OPS)
project in projectsLeadByUser()
project in projectsWhereUserHasPermission("Edit Issues")
issuetype in (Bug, Story)
issuetype in standardIssueTypes()
issuetype in subTaskIssueTypes()
```

Epic / parent:

```jql
parent = PROJ-456                              # Cloud — replaces "Epic Link"
"Epic Link" = PROJ-456                         # DC / Server still uses this
issueLinkType = "is blocked by"
```

## 5. Sprints & boards

```jql
sprint in openSprints()
sprint in closedSprints()
sprint in futureSprints()
sprint = 1337
sprint in (1336, 1337) AND project = PROJ
```

## 6. Status, resolution, priority

```jql
status = "In Progress"
status in ("To Do", "In Progress")
statusCategory != Done                          # broad "still open"
resolution = Unresolved                         # equivalent to legacy "open"
resolution is EMPTY
priority in (Highest, High)
```

## 7. History — `WAS` and `CHANGED`

```jql
# Was ever assigned to me
assignee WAS currentUser()

# Was in In Progress between Mon and Fri
status WAS "In Progress" DURING ("2026-05-26", "2026-05-30")

# Changed status today
status CHANGED DURING (startOfDay(), now())

# Re-opened (Done → anything else)
status CHANGED FROM "Done"

# Changed by a specific person
assignee CHANGED BY "5b10ac…" AFTER -7d
```

## 8. Links, attachments, comments

```jql
issue in linkedIssues("PROJ-123")
issue in linkedIssues("PROJ-123", "blocks")
issueLinkType = "is duplicated by"
attachments is not EMPTY
comment ~ "regression"
```

## 9. Labels, components, versions

```jql
labels = security
labels in (security, urgent)
labels is EMPTY
component = "Checkout"
fixVersion = "2026.06"
affectedVersion in ("2026.05", "2026.04")
fixVersion in unreleasedVersions("PROJ")
fixVersion in releasedVersions("PROJ")
```

## 10. SLAs (Jira Service Management)

```jql
"Time to resolution" = breached()
"Time to first response" = breached()
"Time to resolution" = paused()
```

## 11. Common compound recipes

### "What's on my plate this sprint?"

```jql
assignee = currentUser()
  AND sprint in openSprints()
  AND statusCategory != Done
ORDER BY priority DESC, updated DESC
```

### "Stale issues for triage"

```jql
project = PROJ
  AND statusCategory != Done
  AND updated < -14d
  AND (labels is EMPTY OR labels not in (waiting-on-customer))
ORDER BY updated ASC
```

### "Re-opens this month"

```jql
project = PROJ
  AND status CHANGED FROM "Done" DURING (startOfMonth(), now())
ORDER BY updated DESC
```

### "Bugs introduced in current release"

```jql
project = PROJ AND issuetype = Bug
  AND affectedVersion = "2026.06"
  AND created >= "2026-05-15"
ORDER BY priority DESC
```

### "Things blocking my epic"

```jql
"Epic Link" = PROJ-456
  AND issueLinkType = "is blocked by"
  AND resolution = Unresolved
```

Cloud: replace `"Epic Link" = …` with `parent = …`.

### "Items closed without code review"

```jql
project = PROJ
  AND status = Done
  AND resolved >= -7d
  AND issueFunction not in commented("by membersOf(reviewers)")
```

`issueFunction` requires the **ScriptRunner** add-on. Fall back to manual filtering if it's not installed.

### "Customer-facing tickets needing reply"

```jql
project = SUP
  AND "Request Type" in ("Bug", "Feature request")
  AND status = "Waiting for support"
ORDER BY "Time to first response" ASC
```

### "Anything I follow that moved today"

```jql
watcher = currentUser()
  AND updated >= startOfDay()
ORDER BY updated DESC
```

## 12. Building JQL with the agent — workflow

1. Restate the user's intent in one English sentence.
2. Identify scoping fields: `project`, `issuetype`, time window, people.
3. Add filter conditions one at a time.
4. Always finish with `ORDER BY` (`updated DESC` is a safe default).
5. **Validate** before running on large sites:

   ```bash
   python scripts/search_jql.py --validate --jql '…'
   ```

6. Run with explicit `--fields` to keep payload small.

## 13. Gotchas

- `"="` on text fields silently returns nothing — use `~`.
- `Sprint` accepts numeric IDs, sprint names (`sprint = "Sprint 42"`), or functions. Names with spaces need quotes.
- Custom fields can be referenced by `cf[10016]`, by clauseName (`"Story Points"`), or by ID (`customfield_10016`). Stick to one style.
- `ORDER BY` over a custom field requires the field to be indexed (admin setting on DC).
- `accountId` strings on Cloud must be quoted: `assignee = "5b10ac…"`.
- Reserved words (`Open`, `Done`, etc.) used as project/status names must be quoted.
