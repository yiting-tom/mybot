# agent-folder-override Specification

## Purpose

TBD - created by archiving change 'initial-mybot-fork'. Update Purpose after archive.

## Requirements

### Requirement: Set workspace folder at create time

The `mybot create` command SHALL accept a `--folder PATH` (alias `-f`) option. When supplied, the resolved absolute path (`Path(folder).expanduser().resolve()`) SHALL be written to `agents.defaults.workspace` in the bot's `config.json`.

The folder SHALL be created if it doesn't exist, and bundled templates (HEARTBEAT.md, USER.md, AGENTS.md, SOUL.md, TOOLS.md, memory/MEMORY.md, memory/HISTORY.md) SHALL be synced into it (only files that don't already exist).

#### Scenario: Create with folder pointing to a code repo

- **GIVEN** `~/projects/myrepo` exists
- **WHEN** the user runs `mybot create coding --folder ~/projects/myrepo`
- **THEN** `~/.mybot/workspaces/coding/config.json` has `agents.defaults.workspace = "/Users/<user>/projects/myrepo"`
- **AND** `~/projects/myrepo/HEARTBEAT.md` is created (if missing)
- **AND** `~/projects/myrepo/memory/MEMORY.md` is created (if missing)
- **AND** existing files in the folder are NEVER overwritten

#### Scenario: Create without folder uses default

- **WHEN** the user runs `mybot create coding`
- **THEN** `agents.defaults.workspace` is `""` in the saved config
- **AND** `Config.workspace_path` resolves to `~/.mybot/workspaces/coding/workspace`


<!-- @trace
source: initial-mybot-fork
updated: 2026-05-03
code:
  - CLAUDE.md
  - .spectra.yaml
-->

---
### Requirement: Change workspace folder on an existing bot

Users SHALL change a bot's workspace folder with `mybot <bot_name> set-folder <path>`. The new path SHALL be written into `agents.defaults.workspace` and templates synced (non-destructively) into the new folder.

The literal value `-` SHALL be treated as a sentinel meaning "reset to default" — `agents.defaults.workspace` is set back to the empty string.

#### Scenario: Change folder on existing bot

- **GIVEN** bot `play` exists with default folder
- **WHEN** the user runs `mybot play set-folder ~/Desktop`
- **THEN** `~/.mybot/workspaces/play/config.json` has `agents.defaults.workspace = "/Users/<user>/Desktop"`
- **AND** `mybot list` shows `~/Desktop` in the **Workspace Folder** column for `play`

#### Scenario: Reset folder to default

- **GIVEN** bot `play` has a custom workspace folder set
- **WHEN** the user runs `mybot play set-folder -`
- **THEN** `agents.defaults.workspace` is set to `""`
- **AND** `Config.workspace_path` resolves back to `~/.mybot/workspaces/play/workspace`

#### Scenario: set-folder before bot exists

- **GIVEN** no bot at `~/.mybot/workspaces/missing/`
- **WHEN** the user runs `mybot missing set-folder /tmp`
- **THEN** the command exits with status 1 and prints a message about running `mybot create` first

<!-- @trace
source: initial-mybot-fork
updated: 2026-05-03
code:
  - CLAUDE.md
  - .spectra.yaml
-->