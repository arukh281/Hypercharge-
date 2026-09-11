# Hypercharge architecture

Hypercharge is a repo-native agent platform: graph-first grounding, session memory, and hook enforcement for **Cursor** and **Claude Code**.

## Agent targets

`hypercharge setup --target claude|cursor|both` (default `both`):

| Target | Deploys |
|--------|---------|
| `claude` | `.claude/settings.json` hooks, `CLAUDE.md` managed block, `.claude/skills/repo-guardrail`, lean global skills |
| `cursor` | `.cursor/rules/*.mdc`, `.cursor/hooks.json`, repo guardrail skill |
| `both` | All of the above |

Stored in `.cursor/repo-profile.json` → `agent_target`.

## Dev repo mode

When building Hypercharge itself (`pyproject.toml` name = `hypercharge` + `hypercharge/` package), setup enables **dev_repo**:

- `grounding_gate: warn` — agents edit `hypercharge/`, `tests/`, and project meta without manual `query` seeding
- **Safety unchanged** — `curl`, subshells, and network shell still get HEADS UP advisories (hooks allow; never deny normal edits)
- Consumer repos default `grounding_gate: warn` (advisory) at setup — hooks inform, never deny; `off` disables advisories, `block` opts into Cursor-side enforcement (Claude Code hooks stay advisory regardless)

Override: `"autonomy": {"dev_repo": false}` in `.cursor/repo-profile.json`.

## Layers

| Layer | Modules | Responsibility |
|-------|---------|----------------|
| CLI | `cli.py`, `*_cmd.py` | User and agent commands |
| Deploy | `templates_deploy.py`, `hooks_deploy.py` | Setup wiring, managed rules, hooks |
| Grounding | `grounding_session.py`, `shell_gate.py`, `hook_handlers.py` | Path approval, shell gate, pre-tool policy |
| Memory | `memory_index.py`, `session.py`, `wrapup_cmd.py` | FTS5 session recall, redaction, staleness |
| Graph | `graph.py`, `context.py`, `knowledge_cmd.py` | Code map build, grounded query |
| Safety | `audit_log.py`, `answer_gate.py`, `test_oracle.py` | Advisory audit trail, response grounding, test-result oracle |
| Rules | `compile_cmd.py`, `rules_compile.py` | Optional rules compile, precedence hardening |
| MCP | `mcp_server.py`, `claude_deploy.py` | Grounding tools + session notes, IDE MCP registration |

## Golden path

```
onboard → setup → doctor --tier ready → work → wrapup
```

1. **onboard** — machine install + repo setup; writes `last-onboard.json`
2. **setup** — templates, graph, session, inventory; syncs two managed rules
3. **doctor** — `ready` tier: rules + hooks + memory index freshness
4. **wrapup** — chat/day save; rebuilds memory index

## Hook pipeline

Cursor hooks call `hooks_cmd` → `hook_handlers.dispatch_hook`.  
Claude Code hooks use the same handlers via `claude_hook_adapter` (`hooks --format claude`).

| Event | Cursor | Claude Code | Handler |
|-------|--------|-------------|---------|
| session-start | `sessionStart` | `SessionStart` | `handle_session_start` |
| before-prompt | `beforeSubmitPrompt` | `UserPromptSubmit` | `handle_before_submit_prompt` |
| pre-tool | `preToolUse` | `PreToolUse` | `handle_pre_tool_use` |
| after-edit | `afterFileEdit` | `PostToolUse` (Write\|Edit) | `handle_after_file_edit` |
| Stop | `afterAgentResponse` | `Stop` | `handle_after_agent_response` (grounding + session/commit reminders) |

## Query grounding

`hypercharge query` runs graphify digest; if sparse (no `path:line` citations), **keyword fallback** matches question tokens against `graph.json` node paths and community labels — exits 0 with verified citations without manual `session-grounding.json` seeding.

## Policy

`grounding_policy(root)` reads `repo-profile.json` → `autonomy.grounding_gate` (`block` | `warn` | `off`). Setup deploys `warn` for both dev and consumer repos; the code fallback when the profile is unset is `off`. Pre-tool hooks **advise** and never deny except under opt-in `block`, and even then only on the Cursor surface — the Claude adapter never emits a permission decision.

## Paths

- Graph: `.cursor/graphify-out/`
- Session: `.cursor/session/`
- Runtime: `.cursor/hypercharge/runtime.json`
- Audit: `.cursor/hypercharge/audit.jsonl`
