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

#### Scenario: Cron management on a specific bot

- **WHEN** the user runs `mybot work cron list`
- **THEN** argv is rewritten to `mybot -w work cron list`
- **AND** typer dispatches the cron subcommand against the `work` workspace, NOT the agent with message "cron list"

##### Example: chained subcommand cases

| Input                                | Rewritten                                                     |
| ------------------------------------ | ------------------------------------------------------------- |
| `mybot work`                         | `mybot -w work agent`                                         |
| `mybot work hi`                      | `mybot -w work agent -m "hi"`                                 |
| `mybot work hello world`             | `mybot -w work agent -m "hello world"`                        |
| `mybot work cron list`               | `mybot -w work cron list`                                     |
| `mybot work set-folder /tmp`         | `mybot -w work set-folder /tmp`                               |
| `mybot create work`                  | (unchanged — `create` is reserved)                            |
| `mybot --help`                       | (unchanged — flag at position 0)                              |
| `mybot -w other "hi"`                | (unchanged — flag at position 0; user is being explicit)      |

<!-- @trace
source: initial-mybot-fork
updated: 2026-05-03
code:
  - CLAUDE.md
  - .spectra.yaml
-->