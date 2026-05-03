## MODIFIED Requirements

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
