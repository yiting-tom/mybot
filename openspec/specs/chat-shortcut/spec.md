# chat-shortcut Specification

## Purpose

TBD - created by archiving change 'initial-mybot-fork'. Update Purpose after archive.

## Requirements

### Requirement: First-positional bot-name dispatch

The `mybot` entry point SHALL recognize the form `mybot <bot_name> [args...]` and rewrite argv to `mybot -w <bot_name> agent [-m "<args joined>"]` before the typer dispatcher sees it. This SHALL happen if and only if the first argv token does not start with `-` and is not in the `RESERVED_COMMANDS` set.

The argv pre-processor SHALL fall through to typer unchanged when:
- argv is empty
- the first token starts with `-` (any flag, including `--help`, `--version`, `-w`, `--workspace`)
- the first token is a reserved command (`create`, `delete`, `list`, `agent`, `cron`, `status`, `workspace`, `provider`, `onboard`, `set-folder`)

#### Scenario: Plain chat invocation, interactive

- **WHEN** the user runs `mybot work`
- **THEN** argv is rewritten to `mybot -w work agent`
- **AND** typer dispatches the `agent` command with workspace `work`, entering the interactive REPL

#### Scenario: One-shot message

- **WHEN** the user runs `mybot work "summarize main.py"`
- **THEN** argv is rewritten to `mybot -w work agent -m "summarize main.py"`

#### Scenario: Multi-word message without quotes

- **WHEN** the user runs `mybot work hello world`
- **THEN** argv is rewritten to `mybot -w work agent -m "hello world"`


<!-- @trace
source: initial-mybot-fork
updated: 2026-05-03
code:
  - CLAUDE.md
  - .spectra.yaml
-->

---
### Requirement: Chained subcommand passthrough

When the second argv token is itself a reserved command, the rewriter SHALL produce `mybot -w <bot_name> <reserved_command> [rest...]` instead of treating the rest as a chat message.

The reserved-command set is extended to include `session`. The full set is:
`create`, `delete`, `list`, `agent`, `cron`, `status`, `workspace`, `provider`, `onboard`, `set-folder`, `daemon`, `session`.

#### Scenario: Session list on a specific bot via chat-shortcut

- **WHEN** the user runs `mybot work session list`
- **THEN** argv is rewritten to `mybot -w work session list`
- **AND** typer dispatches the session subcommand against the `work` workspace, NOT the agent with message "session list"

#### Scenario: Session show with key

- **WHEN** the user runs `mybot work session show cli:direct`
- **THEN** argv is rewritten to `mybot -w work session show cli:direct`

#### Scenario: Session clear with flag

- **WHEN** the user runs `mybot work session clear --all -y`
- **THEN** argv is rewritten to `mybot -w work session clear --all -y`

#### Scenario: Existing chained behavior is unchanged

- **WHEN** the user runs `mybot work daemon --once`
- **THEN** argv is rewritten to `mybot -w work daemon --once` (as before)

##### Example: updated chained subcommand cases

| Input                                | Rewritten                                                     |
| ------------------------------------ | ------------------------------------------------------------- |
| `mybot work session list`            | `mybot -w work session list`                                  |
| `mybot work session show cli:direct` | `mybot -w work session show cli:direct`                       |
| `mybot work session clear cron:abc`  | `mybot -w work session clear cron:abc`                        |
| `mybot work session clear --all -y`  | `mybot -w work session clear --all -y`                        |
| `mybot work daemon --once`           | `mybot -w work daemon --once`                                 |
| `mybot work cron list`               | `mybot -w work cron list`                                     |
| `mybot work hello world`             | `mybot -w work agent -m "hello world"`                        |
