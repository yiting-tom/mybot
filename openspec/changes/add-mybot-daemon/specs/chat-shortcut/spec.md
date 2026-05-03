## MODIFIED Requirements

### Requirement: Chained subcommand passthrough

When the second argv token is itself a reserved command, the rewriter SHALL produce `mybot -w <bot_name> <reserved_command> [rest...]` instead of treating the rest as a chat message.

The reserved-command set is extended to include `daemon`. The full set is:
`create`, `delete`, `list`, `agent`, `cron`, `status`, `workspace`, `provider`, `onboard`, `set-folder`, `daemon`.

#### Scenario: Daemon on a specific bot via chat-shortcut

- **WHEN** the user runs `mybot work daemon`
- **THEN** argv is rewritten to `mybot -w work daemon`
- **AND** typer dispatches the daemon command against the `work` workspace, NOT the agent with message "daemon"

#### Scenario: Daemon flags pass through

- **WHEN** the user runs `mybot work daemon --once`
- **THEN** argv is rewritten to `mybot -w work daemon --once`

#### Scenario: Existing chained behavior is unchanged

- **WHEN** the user runs `mybot work cron list`
- **THEN** argv is rewritten to `mybot -w work cron list` (as before)

##### Example: updated chained subcommand cases

| Input                                | Rewritten                                                     |
| ------------------------------------ | ------------------------------------------------------------- |
| `mybot work daemon`                  | `mybot -w work daemon`                                        |
| `mybot work daemon --once`           | `mybot -w work daemon --once`                                 |
| `mybot work cron list`               | `mybot -w work cron list`                                     |
| `mybot work hello world`             | `mybot -w work agent -m "hello world"`                        |
