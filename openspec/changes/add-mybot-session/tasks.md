## 1. SessionManager additions (`delete()` lives on `SessionManager`, not in the CLI; Path resolution: trust `Config.workspace_path`)

- [x] 1.1 Add `SessionManager.delete(key) -> bool` that calls `_get_session_path(key).unlink(missing_ok=True)`, calls `self.invalidate(key)`, returns whether a file was actually removed — implements the SessionManager.delete() requirement; `delete()` lives on `SessionManager`, not in the CLI
- [x] 1.2 Augment `SessionManager.list_sessions()` to include `message_count` (count of records with `_type != "metadata"`) and `size_bytes` (`path.stat().st_size`) in each returned dict — implements the list_sessions reports counts and sizes requirement
- [x] 1.3 Implement counting by streaming the JSONL once: parse each line as JSON, increment `message_count` when `_type` is missing or not `"metadata"`. Skip malformed lines silently
- [x] 1.4 Verify backward compatibility: existing callers (`AgentLoop._pick_heartbeat_target` in nanobot's old gateway, etc.) still get `key`/`updated_at` — only adding fields, never removing

## 2. CLI sub-app scaffold (`session` is a typer sub-app, not flat commands)

- [x] 2.1 Add `RESERVED_COMMANDS.add("session")` so chained dispatch works — implements the modified Chained subcommand passthrough requirement
- [x] 2.2 Create `session_app = typer.Typer(help="Manage conversation history")` and `app.add_typer(session_app, name="session")`, mirroring the existing `cron_app` pattern
- [x] 2.3 Verify chat-shortcut chain: `mybot work session --help` reaches the new sub-app

## 3. `session list` command — List sessions for a bot (`list` shows updated time, message count, size; Output format guarantees for `list`)

- [x] 3.1 `@session_app.command("list")` body: load `Config`, instantiate `SessionManager(config.workspace_path)`, call `list_sessions()` — implements the List sessions for a bot requirement
- [x] 3.2 If the returned list is empty, print `No sessions for bot '<bot_label>'` and return — covers the Empty state scenario
- [x] 3.3 Build a `rich.table.Table(title=f"Sessions for '<bot_label>'")` with columns Key, Updated, Messages, Size
- [x] 3.4 Format updated_at as `YYYY-MM-DD HH:MM` (parse ISO timestamp); format size_bytes via a `_humanize_bytes` helper (B/KB/MB/GB with one decimal)
- [x] 3.5 Sessions are already sorted by updated_at desc inside list_sessions — preserve that order
- [x] 3.6 Render table — Rich auto-detects TTY-vs-pipe so plain whitespace output is automatic when piped (Output format guarantees)

## 4. `session show` command — Show one session (`show` renders by role with timestamps)

- [x] 4.1 `@session_app.command("show")` body: arg `key: str`, option `--max INT | None` — implements the Show one session requirement
- [x] 4.2 Use `SessionManager._get_session_path(key)` (or copy the same `safe_filename` logic into a public helper) — if file does not exist, exit 1 with `Session '<key>' not found` — covers the Missing session scenario
- [x] 4.3 Stream the JSONL: skip the first line if it is metadata; parse subsequent lines as message dicts
- [x] 4.4 If `--max N` given, accumulate into a deque(maxlen=N) and render only those at the end; otherwise render as we go
- [x] 4.5 For each message: print `[<role> <timestamp_or_?>]` then the content body. Use `console.print` (Rich)
- [x] 4.6 If role is `tool` and content length > 200, truncate to 200 chars + `…(truncated)` — implements the Tool message truncation scenario
- [x] 4.7 Skip empty/null content gracefully (don't crash on `None`)

## 5. `session clear` command — Clear sessions (`clear` deletes the JSONL file outright)

- [x] 5.1 `@session_app.command("clear")` body: arg `key: Optional[str] = typer.Argument(None)`, options `--all` (bool) and `-y/--yes` (bool) — implements the Clear sessions requirement
- [x] 5.2 Validate: exactly one of `key` or `--all` must be provided — error "Provide either <key> or --all" otherwise
- [x] 5.3 For `--all`: glob `<workspace>/sessions/*.jsonl` (top-level only, no recursion). If empty list → print `No sessions to clear`, exit 0. Otherwise prompt unless `-y`, then unlink each and call `SessionManager.invalidate` for each derived key — covers the Subdirectories are preserved and No-op-on-empty scenarios
- [x] 5.4 For single-key form: call `SessionManager.delete(key)`. If it returns False → exit 1 with `Session '<key>' not found`. Otherwise prompt unless `-y`, then delete
- [x] 5.5 Use `typer.confirm("This will permanently delete N session(s). Continue?")` for confirmation; on declined → print `Cancelled.` and `raise typer.Exit()`
- [x] 5.6 Print `✓ Cleared session '<key>'` or `✓ Cleared N session(s)` on success

## 6. README updates

- [x] 6.1 Under "Chatting with a bot": add a one-liner pointing at `mybot <bot> session list/show/clear` for managing history without entering the REPL
- [x] 6.2 Add a new mini-section `### Sessions` under the chat docs (or right after) explaining the relationship between `/new` (in-REPL) and `mybot <bot> session clear` (out-of-REPL)
- [x] 6.3 Extend the CLI reference block with three new lines for `session list / show <key> / clear [<key>|--all] [-y]`
- [x] 6.4 Update the roadmap: check off `mybot session list/show/clear`

## 7. Manual smoke verification

- [x] 7.1 `mybot create scratch --folder /tmp/mybot-session-test` succeeds; `mybot scratch session list` prints `No sessions for bot 'scratch'`
- [x] 7.2 Drop a synthetic JSONL into `/tmp/mybot-session-test/sessions/cli_direct.jsonl` (metadata + a few user/assistant/tool messages); `mybot scratch session list` shows it with correct count + size
- [x] 7.3 `mybot scratch session show cli:direct` renders the messages with timestamp brackets
- [x] 7.4 `mybot scratch session show cli:direct --max 1` renders only the last message
- [x] 7.5 `mybot scratch session clear cli:direct -y` removes the file; subsequent `session list` is empty again
- [x] 7.6 Drop two more sessions; `mybot scratch session clear --all -y` removes both; subdir `archived/` (manually created) is untouched
- [x] 7.7 `mybot scratch session clear ghost -y` exits 1 with `Session 'ghost' not found`
- [x] 7.8 Tear down: `mybot delete scratch -y`, `rm -rf /tmp/mybot-session-test`

## 8. Spectra archival

- [x] 8.1 `spectra validate add-mybot-session` is clean
- [x] 8.2 `spectra analyze add-mybot-session` has no Critical/Warning findings
- [ ] 8.3 Commit + push
- [ ] 8.4 `spectra archive add-mybot-session`
