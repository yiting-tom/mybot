## ADDED Requirements

### Requirement: List sessions for a bot

The `mybot <bot> session list` command SHALL print a table of all sessions belonging to the active bot. Sessions are the JSONL files under `<config.workspace_path>/sessions/`. The table SHALL include columns:

- **Key** — the session key (e.g., `cli:direct`, `cron:1a2b3c4d`, `heartbeat`)
- **Updated** — the `updated_at` timestamp from the metadata line, formatted `YYYY-MM-DD HH:MM`
- **Messages** — the number of message records (excluding the metadata line)
- **Size** — the on-disk file size in human-readable units (e.g., `48.2 KB`)

Rows SHALL be sorted by **Updated** descending (most recent first). When there are no sessions, the command SHALL print `No sessions for bot '<bot>'` and exit 0.

#### Scenario: Multiple sessions present

- **GIVEN** bot `work` has sessions `cli:direct` (last updated 2026-05-03 14:32, 127 messages, 48.2 KB) and `cron:abc` (last updated 2026-05-02 09:15, 12 messages, 3.1 KB)
- **WHEN** the user runs `mybot work session list`
- **THEN** the table shows both rows with `cli:direct` first

##### Example: rendered list output

```
       Sessions for 'work'
┏━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━┓
┃ Key           ┃ Updated          ┃ Messages ┃ Size    ┃
┡━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━╇━━━━━━━━━┩
│ cli:direct    │ 2026-05-03 14:32 │      127 │ 48.2 KB │
│ heartbeat     │ 2026-04-30 18:00 │       45 │ 12.7 KB │
│ cron:1a2b3c4d │ 2026-05-02 09:15 │       12 │  3.1 KB │
└───────────────┴──────────────────┴──────────┴─────────┘
```

#### Scenario: Empty state

- **GIVEN** bot `notes` has no sessions on disk
- **WHEN** the user runs `mybot notes session list`
- **THEN** stdout contains `No sessions for bot 'notes'`
- **AND** the exit code is 0

### Requirement: Show one session

The `mybot <bot> session show <key>` command SHALL render the contents of one session in human-readable form. Each message record SHALL be printed as:

```
[<role> <timestamp>]
<content>
```

Where:
- `<role>` is `user`, `assistant`, `tool`, or `system`.
- `<timestamp>` is `YYYY-MM-DD HH:MM:SS` derived from the message's `timestamp` field; missing timestamps render as `?`.
- Tool messages SHALL be truncated to 200 characters in the rendered output, with a `…(truncated)` suffix when truncation occurs.

The command SHALL accept `--max N` to render only the last N message records (default unlimited). The metadata line SHALL NOT be rendered.

If the named session does not exist the command SHALL exit 1 with `Session '<key>' not found`.

#### Scenario: Render last 3 messages

- **GIVEN** bot `work` has session `cli:direct` with 50 messages
- **WHEN** the user runs `mybot work session show cli:direct --max 3`
- **THEN** only the last 3 messages render, in order

#### Scenario: Tool message truncation

- **GIVEN** a session contains a `tool` message of 5,000 characters
- **WHEN** the user runs `mybot <bot> session show <key>`
- **THEN** that message renders as the first 200 characters followed by `…(truncated)`
- **AND** the on-disk JSONL file is unchanged

#### Scenario: Missing session

- **WHEN** the user runs `mybot work session show ghost`
- **AND** no file `cli/sessions/ghost.jsonl` exists
- **THEN** the command exits with status 1
- **AND** prints `Session 'ghost' not found`

##### Example: rendered show output

```
[user 2026-05-03 14:31:02]
help me debug the import error in main.py

[assistant 2026-05-03 14:31:05]
Let me read the file.

[tool 2026-05-03 14:31:08]
{"result": "from foo import bar\n..."}…(truncated)

[assistant 2026-05-03 14:31:12]
The issue is on line 42 — you're importing `foo` from `bar`...
```

### Requirement: Clear sessions

The `mybot <bot> session clear <key>` command SHALL delete the JSONL file backing the named session and remove it from the in-memory cache. The default behavior SHALL prompt for confirmation; the `-y` / `--yes` flag SHALL skip the prompt.

The `mybot <bot> session clear --all` form SHALL delete every JSONL file in `<config.workspace_path>/sessions/`. Always confirms unless `-y`. When the directory is empty, the command SHALL print `No sessions to clear` and exit 0.

Clearing SHALL NOT recurse into subdirectories. Only top-level `*.jsonl` files in the sessions dir are removed.

Clearing a non-existent session SHALL exit 1 with `Session '<key>' not found`.

#### Scenario: Clear one session, confirmed

- **GIVEN** bot `work` has session `cron:abc`
- **WHEN** the user runs `mybot work session clear cron:abc` and types `y`
- **THEN** the file `cron_abc.jsonl` is removed
- **AND** the next `mybot work session list` does not include `cron:abc`

#### Scenario: Clear all with -y skips prompt

- **GIVEN** bot `work` has 5 sessions
- **WHEN** the user runs `mybot work session clear --all -y`
- **THEN** all 5 JSONL files are removed
- **AND** the command exits 0

#### Scenario: Clear all on empty dir

- **GIVEN** bot `notes` has no sessions
- **WHEN** the user runs `mybot notes session clear --all`
- **THEN** stdout contains `No sessions to clear`
- **AND** no prompt is shown
- **AND** the exit code is 0

#### Scenario: Clear missing session

- **WHEN** the user runs `mybot work session clear ghost -y`
- **THEN** the command exits 1
- **AND** prints `Session 'ghost' not found`

#### Scenario: Subdirectories are preserved

- **GIVEN** the sessions dir contains `cli_direct.jsonl` and a subdir `archived/`
- **WHEN** the user runs `mybot work session clear --all -y`
- **THEN** `cli_direct.jsonl` is deleted
- **AND** `archived/` and its contents are preserved

### Requirement: SessionManager.delete()

`SessionManager.delete(key: str) -> bool` SHALL be added. It SHALL `unlink` the session's backing file (with `missing_ok=True`), invalidate the in-memory cache for that key, and return `True` if a file was removed, `False` otherwise. This method SHALL be the only sanctioned way for callers outside `SessionManager` to remove a session.

#### Scenario: Delete existing session

- **GIVEN** session `cli:direct` exists on disk
- **WHEN** `SessionManager.delete("cli:direct")` is called
- **THEN** the JSONL file is removed
- **AND** the cache no longer contains `cli:direct`
- **AND** the return value is `True`

#### Scenario: Delete missing session

- **WHEN** `SessionManager.delete("ghost")` is called and no such file exists
- **THEN** the cache is unchanged
- **AND** the return value is `False`

### Requirement: list_sessions reports counts and sizes

`SessionManager.list_sessions()` SHALL include `message_count` (int, count of records with `_type != "metadata"`) and `size_bytes` (int, the file's stat size) in each returned dict, in addition to the existing `key`, `created_at`, `updated_at`, `path` fields.

#### Scenario: Counts exclude the metadata line

- **GIVEN** session `cli:direct` has 1 metadata line + 12 message lines
- **WHEN** `list_sessions()` is called
- **THEN** the returned dict for `cli:direct` has `message_count = 12`
- **AND** `size_bytes` matches the file's `st_size`
