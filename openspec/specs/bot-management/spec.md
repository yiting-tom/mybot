# bot-management Specification

## Purpose

TBD - created by archiving change 'initial-mybot-fork'. Update Purpose after archive.

## Requirements

### Requirement: Create bot

Users SHALL create a new bot with `mybot create [bot_name] [--folder PATH]`. Without `bot_name`, the default bot at `~/.mybot/` is initialized. With `bot_name`, the bot's data dir is `~/.mybot/workspaces/<bot_name>/`. The optional `--folder` flag SHALL persist into `agents.defaults.workspace` so the agent operates in that directory.

If a bot already exists at the target data dir, the command SHALL prompt to overwrite (`y` = reset to defaults) or refresh (`N` = keep existing values, add new fields).

#### Scenario: Create a new named bot with a custom folder

- **WHEN** the user runs `mybot create coding --folder ~/projects/myrepo`
- **THEN** `~/.mybot/workspaces/coding/config.json` is created
- **AND** the config has `agents.defaults.workspace = "/Users/<user>/projects/myrepo"` (resolved absolute)
- **AND** `~/projects/myrepo` is created if it didn't exist
- **AND** template files (HEARTBEAT.md, USER.md, AGENTS.md, SOUL.md, TOOLS.md, memory/MEMORY.md, memory/HISTORY.md) are written into `~/projects/myrepo` if not already present

#### Scenario: Create the default bot

- **WHEN** the user runs `mybot create`
- **THEN** `~/.mybot/config.json` is created
- **AND** the workspace folder defaults to `~/.mybot/workspace`


<!-- @trace
source: initial-mybot-fork
updated: 2026-05-03
code:
  - CLAUDE.md
  - .spectra.yaml
-->

---
### Requirement: List bots

Users SHALL list all bots with `mybot list`. The output table SHALL include the default bot, every named bot under `~/.mybot/workspaces/`, each one's data dir, each one's resolved workspace folder, and a marker for the active bot.

#### Scenario: List with multiple named bots

- **GIVEN** bots `coding` (folder = ~/projects/myrepo) and `notes` (default folder) exist
- **WHEN** the user runs `mybot list`
- **THEN** the output is a table with rows for `(default)`, `coding`, `notes`, in that order
- **AND** the **Workspace Folder** column shows the resolved absolute path per bot


<!-- @trace
source: initial-mybot-fork
updated: 2026-05-03
code:
  - CLAUDE.md
  - .spectra.yaml
-->

---
### Requirement: Delete bot

Users SHALL delete a named bot with `mybot delete <bot_name> [-y]`. The default bot CANNOT be deleted via this command. The command SHALL only remove the data dir under `~/.mybot/workspaces/<bot_name>/`. A user-supplied workspace folder set via `--folder` is NEVER removed.

#### Scenario: Delete with confirmation

- **GIVEN** bot `tmp` exists
- **WHEN** the user runs `mybot delete tmp` and types `y`
- **THEN** `~/.mybot/workspaces/tmp/` is removed
- **AND** the user-supplied workspace folder (if any) is preserved

#### Scenario: Delete with `-y` skips confirmation

- **WHEN** the user runs `mybot delete tmp -y`
- **THEN** the data dir is removed without a prompt

#### Scenario: Delete missing bot

- **WHEN** the user runs `mybot delete nonexistent`
- **THEN** the command exits with status 1 and prints `Bot 'nonexistent' not found`

<!-- @trace
source: initial-mybot-fork
updated: 2026-05-03
code:
  - CLAUDE.md
  - .spectra.yaml
-->