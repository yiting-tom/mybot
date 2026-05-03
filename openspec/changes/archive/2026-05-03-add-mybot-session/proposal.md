## Why

Every bot persists its conversations as JSONL files under `<data_dir>/sessions/`. Each interactive REPL, each `mybot <bot> "<msg>"`, each cron-driven turn, and the heartbeat each get their own session keyed by `<channel>:<chat_id>` — `cli:direct`, `cron:1a2b3c4d`, `heartbeat`, etc.

Today these files accumulate silently. There's no way from the CLI to:
- See which sessions exist and how big they are.
- Inspect what was actually said in a particular session (without `cat`-ing JSONL by hand).
- Clear stale sessions without `rm`.

For a daily-driver assistant this is unacceptable. The user can't audit what the bot remembers, can't recover from a poisoned session except by knowing the on-disk layout, and can't selectively prune cron-driven session history that piles up over weeks.

`SessionManager.list_sessions()` already exists — we just don't expose it. `Session.clear()` exists too. The agent-internal `/new` command archives the active session, but only from inside the REPL.

## What Changes

- **New CLI subcommand `mybot <bot> session`** with three operations:
  - `mybot <bot> session list` — table of session keys, last-updated time, message count, file size.
  - `mybot <bot> session show <key>` — pretty-print the conversation (role, timestamp, content) for one session, with optional `--max N` to tail the last N turns.
  - `mybot <bot> session clear <key>` — delete one session's JSONL file (confirms unless `-y`).
  - `mybot <bot> session clear --all` — delete every session under the bot's data dir (always confirms unless `-y`).
- **Add `session` to `RESERVED_COMMANDS`** so `mybot work session list` chains through the chat-shortcut.
- **Add `SessionManager.delete(key) -> bool`** — small helper since today only `clear()` (which mutates in memory but doesn't unlink) and `invalidate()` (cache-only) exist. Symmetric with `save()`.
- **Augment `SessionManager.list_sessions()`** to also report `message_count` and `size_bytes` for each session, so the table view doesn't have to re-stat files.
- **Update README**: expand the existing "Chatting with a bot" section to mention `/new` vs. `mybot <bot> session clear`, add a Sessions reference under CLI reference.

## Non-Goals

- **No editing of in-flight session content.** If you want to surgically remove a poisoned message, you still edit the JSONL file. The CLI offers wholesale operations only.
- **No export to a chat transcript format** (Markdown, HTML, ChatGPT-export shape). `show` prints to stdout; users pipe through their own formatter.
- **No multi-bot operations.** Each invocation targets exactly one bot. Cleaning across all bots is shell-loopable: `for b in $(mybot list ...); do mybot $b session clear --all -y; done`.
- **No undo.** Deletes are immediate and unrecoverable. The confirmation prompt is the safety net.
- **No global "consolidation" command** — the existing memory consolidation (triggered automatically when a session crosses `memoryWindow`, and by `/new` from inside the REPL) stays as-is. We're not exposing it as a separate CLI verb in this change.

## Capabilities

### New Capabilities

- `session-management`: CLI surface for listing, inspecting, and pruning the on-disk session JSONL files of a bot.

### Modified Capabilities

- `chat-shortcut`: `session` joins the `RESERVED_COMMANDS` set so `mybot <bot> session ...` chains rather than being rewritten as a chat message.

## Impact

- Affected specs: `session-management` (new), `chat-shortcut` (modified — reserved word list grows by one).
- Affected code:
  - Modified: mybot/session/manager.py (new `delete()` method; `list_sessions()` reports message_count + size_bytes)
  - Modified: mybot/cli/commands.py (new `session_app` typer subcommand; `RESERVED_COMMANDS` adds `session`)
  - Modified: README.md (CLI reference + a small Sessions section under chat docs)
- External: no new dependencies. Uses existing `SessionManager`, `rich.table.Table`, and stdlib only.
