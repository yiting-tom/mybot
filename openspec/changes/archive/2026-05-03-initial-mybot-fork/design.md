## Context

We started from upstream [nanobot](https://github.com/HKUDS/nanobot) at v0.1.4.post3. nanobot's design is good — small core, pluggable providers, clean session/memory split — but its 10 chat-platform clients dominate the dependency surface and shape its CLI (`gateway`, `channels` subcommand) and config schema (`ChannelsConfig` with 10 nested models).

Our actual usage pattern is one terminal + one agent per project. The natural unit is therefore a **bot** (= a config + sessions + cron + agent workspace), and there should be many of them. We also want bots to operate inside arbitrary folders (a code repo, a notes dir) without the agent's bookkeeping leaking into that folder.

## Goals / Non-Goals

**Goals**

- Subtractive: keep nanobot's agent core unchanged so future upstream merges stay tractable.
- Additive: multi-bot lifecycle, chat shortcut, decoupled workspace folder.
- Friendly default UX: `mybot <name>` should "just chat" — the most common operation needs no subcommand.
- All bot data is isolated; deleting one bot can't affect another.

**Non-Goals**

- Re-introducing channels in a different form (REST, web UI, daemon-as-bridge). Out of scope.
- Process-level multi-bot orchestration. Each `mybot` invocation targets exactly one bot.
- Migrating from nanobot's `~/.nanobot/` automatically.

## Decisions

### 1. Keep the `channel:chat_id` plumbing string

We considered ripping the `channel` field out of `InboundMessage` / `OutboundMessage` / session keys. It would be cleaner conceptually but invasive — every method on `AgentLoop`, `SessionManager`, and the bus uses `f"{channel}:{chat_id}"` as a routing key, and subagents rely on it for origin tracking.

We instead pinned `channel` to `"cli"` (or `"system"` for subagent → parent messages). Saves ~200 lines of refactor and zero functional change. The cost is one weird-looking field in the message schema, which we documented as "routing tag (e.g. cli, system)".

### 2. Two-level addressing: data dir vs workspace folder

A bot has:

- **Data dir** — `~/.mybot/workspaces/<name>/` (or `~/.mybot/` for the unnamed default). Contains `config.json`, `cron/jobs.json`, `sessions/`, `history/cli_history`. Owned and managed by mybot.
- **Workspace folder** — defaults to `<data_dir>/workspace` but can be any path. Contains `HEARTBEAT.md`, `memory/MEMORY.md`, `memory/HISTORY.md`, `skills/`, the agent's working files. Surfaced in the agent's runtime context.

This split lets a user run `mybot create coding --folder ~/projects/repo`. The agent edits files in `repo/` while bot bookkeeping stays in `~/.mybot/workspaces/coding/`. Reverse arrangement (mixing both) was rejected because chat history doesn't belong inside a tracked code repo.

The folder lives in `agents.defaults.workspace` (existing nanobot field). Empty string means "use default".

### 3. Workspace resolver is a small pure function

`resolve_data_dir(workspace: str | None) -> Path`:

- `None` → check `MYBOT_WORKSPACE` env, else `~/.mybot/`.
- Contains `/` `\` or starts with `~`/`.` → treat as path → `Path(arg).expanduser().resolve()`.
- Otherwise → `~/.mybot/workspaces/<arg>/`.

Heuristic-based name vs path detection beats requiring a flag like `--workspace-path`. We accept the minor edge case that a bot named `./foo` or `foo/bar` would be misparsed — both are bad bot names anyway.

The resolved path is set process-wide via `set_active_data_dir`, so every helper (`get_data_path`, `get_config_path`, `Config.workspace_path`) reads the same value without threading a context object through the call graph.

### 4. Chat shortcut is an argv pre-processor, not a typer command

Typer's natural model is `<command> [args]`. To make `mybot <bot_name> [message]` work, we rewrite argv before typer dispatches:

```
mybot work hello world  →  mybot -w work agent -m "hello world"
mybot work cron list    →  mybot -w work cron list
mybot create work       →  (untouched — `create` is reserved)
```

The rewriter runs in `run()` (the new `pyproject.toml` script entry). It bails out if the first token is a flag (so `mybot --help` works) or a reserved subcommand. A `RESERVED_COMMANDS` set is the canonical list.

We considered click's `invoke_without_command` callbacks instead. Rejected because they don't compose well with typer's auto-help and would require re-implementing argv splitting anyway.

### 5. `set-folder -` as a sentinel for reset

We needed a way to revert a custom workspace folder back to the default without manually editing JSON. Considered:

- `set-folder` with no argument → reset. Confusing — looks like "show current".
- `--reset` flag — adds API surface for one rare action.
- Sentinel value `"-"` — chosen. Common Unix convention (stdin), short, unambiguous (no real path is `-`).

## Risks / Trade-offs

| Risk | Mitigation |
|------|------------|
| Heuristic name-vs-path detection misclassifies edge cases like `mybot -w foo.bar` (treated as path because of `.`) | Document the rule; reserve dotted names as a known sharp edge. Unlikely in practice. |
| `channel` field staying in events.py is a vestigial concept that may confuse future readers | Comment makes the constraint explicit ("routing tag — `cli` or `system`"). If we ever add another transport this concept is the natural extension point. |
| `RESERVED_COMMANDS` must stay in sync with the actual command list — adding a top-level command without updating it would silently shadow bot names | Add a runtime self-check (introspect `app.registered_commands`) before next release. Tracked as a follow-up. |
| Argv pre-processor doesn't see typer's help / completion machinery, so `mybot <TAB>` won't suggest bot names | Acceptable — completion can be added later by emitting a custom completion script. |
| Custom workspace folder means agent file tools can read/write outside `~/.mybot/`. If `restrictToWorkspace=true`, the sandbox is the user-set folder, not the data dir | Documented. This is the desired behavior — the user is explicit about pointing the agent at a directory. |
| Deleting a bot via `mybot delete <name>` removes its data dir but does **not** touch a custom workspace folder pointed at by `--folder` | Documented. We won't delete files we didn't create. |
