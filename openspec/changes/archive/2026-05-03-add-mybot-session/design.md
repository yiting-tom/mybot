## Context

`SessionManager` (`mybot/session/manager.py`) already owns the on-disk format: one JSONL file per session at `<workspace>/sessions/<safe_key>.jsonl`. The first line is a metadata record (`{"_type": "metadata", "key", "created_at", "updated_at"}`), subsequent lines are message dicts. `list_sessions()` reads only the metadata line per file, so it's cheap to scan even with hundreds of sessions.

Sessions are scoped per *workspace folder*, not per *data dir* — i.e., they live next to the agent's `memory/` and `skills/`, inside whichever directory `Config.workspace_path` resolves to. This matters because `--folder` users have sessions inside their project folder, default users have them inside `<data_dir>/workspace/sessions/`. The CLI commands need to delegate path resolution to the existing `Config.workspace_path` and `SessionManager(workspace)` constructor so they always agree with where the agent actually writes.

The agent-internal `/new` command (in `AgentLoop._process_message`) handles "archive the current session and start fresh" *while a chat is in progress*. The CLI commands handle "manage history without entering a chat" — they're complementary, not redundant.

## Goals / Non-Goals

**Goals**

- Three small read-only-or-destructive verbs that map cleanly to existing `SessionManager` capabilities.
- Output suitable for piping (`mybot work session show cli:direct | grep TODO`) and for terminal viewing (rich rendering).
- Every destructive operation confirms by default, with a `-y` escape hatch for scripts.
- Multi-bot isolation: a `session clear` against `work` never touches `notes`.

**Non-Goals**

- Editing within sessions (partial truncation, message rewrites).
- Cross-bot operations (`mybot session list` without a bot context — out of scope; users loop in shell).
- Export to non-JSONL formats. `show` is a viewer, not a converter.
- Search across sessions. Users grep the JSONL files directly.
- Undo / trash. Deletes are immediate.

## Decisions

### 1. `session` is a typer sub-app, not flat commands

Like `cron` (`mybot cron list / add / remove / enable / run`), `session` gets its own `typer.Typer` registered as `app.add_typer(session_app, name="session")`. Verbs: `list`, `show`, `clear`. Mirrors the cron mental model.

Alternative considered: flat `mybot session-list / session-show / session-clear` as siblings of `create`/`delete`. Rejected — it pollutes the top-level command space with three more entries and breaks the "one noun, many verbs" pattern that cron already established.

### 2. `list` shows updated time, message count, size

Columns:

```
Key             Updated              Messages  Size
cli:direct      2026-05-03 14:32       127     48.2 KB
cron:1a2b3c4d   2026-05-02 09:15        12      3.1 KB
heartbeat       2026-04-30 18:00        45     12.7 KB
```

Sorted by `updated_at` desc — most recent at the top. Empty state: `No sessions for bot '<name>'`.

`list_sessions()` is augmented to walk past the metadata line and count subsequent records (skipping `_type=="metadata"`). Implementation reads the file twice would be wasteful, so we count via line iteration and stat once. The cost is one full file scan per session, which is fine at the scale of "a few hundred sessions per bot."

### 3. `show` renders by role with timestamps

```
[user 2026-05-03 14:31:02]
help me debug the import error in main.py

[assistant 2026-05-03 14:31:05]
Let me read the file.

[tool web_search 2026-05-03 14:31:08]
{...truncated to first 200 chars...}

[assistant 2026-05-03 14:31:12]
The issue is on line 42 — you're importing `foo` from `bar`, but...
```

Tool results are truncated to 200 chars in the rendered view to keep things scannable; raw JSONL is on disk if you need more. `--max N` shows only the last N message records (default unlimited).

We render via `rich.console.Console.print` with role-prefixed lines, not Markdown — Markdown rendering would mangle code blocks that themselves contain `[role]`-style headers. Plain prefixed lines also pipe better to `grep`.

### 4. `clear` deletes the JSONL file outright

Two forms:

- `mybot <bot> session clear <key>` — deletes one. Confirms by default; `-y` skips.
- `mybot <bot> session clear --all` — deletes every JSONL in the sessions dir. Always confirms unless `-y`. Empty dir → no-op message.

Adding `--all` upfront is intentional — without it, scripting multi-key cleanup is awkward. Both invocations call `SessionManager.delete(key)`, which `unlink(missing_ok=True)`s the file and `invalidate()`s the cache so a subsequent `mybot work` doesn't resurrect a stale in-memory copy.

We chose `clear` over `delete` for the verb because:
1. It mirrors the in-REPL `/new` (which clears state).
2. `delete` at the top level already means "delete a bot" — reusing it under `session` would be semantically muddy.

### 5. `delete()` lives on `SessionManager`, not in the CLI

Pattern follows `save()` / `invalidate()`. The CLI shouldn't reach inside `_get_session_path()`. Test/audit benefit: the session lifecycle stays in one place.

```python
def delete(self, key: str) -> bool:
    path = self._get_session_path(key)
    if not path.exists():
        return False
    path.unlink()
    self.invalidate(key)
    return True
```

### 6. Path resolution: trust `Config.workspace_path`

Both new CLI commands instantiate `SessionManager(config.workspace_path)` — the same call AgentLoop makes. This guarantees the user's view through `mybot session list` exactly matches where the agent reads/writes. We do NOT scan multiple candidate dirs (default + workspace_path) — the agent has been writing to `workspace_path` for the whole life of this fork, so there's nothing else to find.

### 7. Output format guarantees for `list`

```
Key             Updated              Messages  Size
```

When stdout is a TTY → rich `Table` with colored "Updated" column.
When piped → plain whitespace-separated rows; rich auto-detects.

Rationale: parity with `mybot list` and `mybot cron list`. Rich already auto-detects this.

## Risks / Trade-offs

| Risk | Mitigation |
|------|------------|
| Counting messages requires a full file read; at thousands of sessions × thousands of messages, `session list` could be slow | Acceptable at design scale. If it ever matters, cache `(mtime, count)` in metadata. Out of scope here. |
| User runs `session clear --all -y` and loses cron-driven history they wanted | Documented. The default is "always confirm." `-y` is opt-in. |
| `session show` for a poisoned session is large enough to flood the terminal | `--max N` flag handles this. Default is "show everything" (matches Unix convention; `head -100` if you want less). |
| Tool messages in JSONL include large blobs (file reads, web fetches) — pretty-rendering them all bloats output | Truncate tool message rendering to 200 chars. Raw is still on disk. |
| Concurrent `mybot work daemon` writing while `session show` is reading the same file | JSONL is append-only and line-oriented; partial last-line risk is negligible. We do NOT take a file lock. |
| Sessions live under `Config.workspace_path` but a user might point that path at a code repo (`--folder ~/projects/repo`) — `session clear --all` there could surprise | The sessions dir is always `<workspace_path>/sessions/`, never anything else. We only delete files matching `*.jsonl` in that exact dir. We do NOT recurse. |
| `SessionManager` has a legacy `~/.mybot/sessions/` migration path; new commands ignore it | Out of scope — that legacy dir is a no-op for fresh mybot installs. If it has files, the user can find them by hand. |
| Adding `session` to `RESERVED_COMMANDS` shadows a (theoretical) bot named `session` | Documented. `session` joins the existing reserved list. Bot names should not collide with subcommand names. |
