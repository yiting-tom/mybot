# workspace-resolution Specification

## Purpose

TBD - created by archiving change 'initial-mybot-fork'. Update Purpose after archive.

## Requirements

### Requirement: Resolve a workspace argument to a data directory

The function `resolve_data_dir(workspace: str | None) -> Path` SHALL deterministically map a workspace argument to an absolute data directory using these rules, evaluated in order:

1. If `workspace` is `None`, fall back to the value of the `MYBOT_WORKSPACE` environment variable.
2. If still empty, return `~/.mybot/`.
3. If the value contains `/` or `\`, or starts with `~` or `.`, treat it as a path: return `Path(value).expanduser().resolve()`.
4. Otherwise, treat it as a name: return `~/.mybot/workspaces/<value>/`.

#### Scenario: No workspace argument and no env var

- **GIVEN** `MYBOT_WORKSPACE` is unset
- **WHEN** `resolve_data_dir(None)` is called
- **THEN** the result is `Path.home() / ".mybot"`

#### Scenario: Named workspace

- **WHEN** `resolve_data_dir("work")` is called
- **THEN** the result is `Path.home() / ".mybot" / "workspaces" / "work"`

#### Scenario: Explicit absolute path

- **WHEN** `resolve_data_dir("/tmp/sandbox")` is called
- **THEN** the result is `Path("/tmp/sandbox").resolve()`

#### Scenario: Tilde expansion

- **WHEN** `resolve_data_dir("~/projects/foo")` is called
- **THEN** the result is the user's home dir + `/projects/foo`

#### Scenario: Env var fallback

- **GIVEN** `MYBOT_WORKSPACE=play` is set
- **WHEN** `resolve_data_dir(None)` is called
- **THEN** the result is `Path.home() / ".mybot" / "workspaces" / "play"`

##### Example: resolution table

| Input                | `MYBOT_WORKSPACE` | Resolved data dir                          |
| -------------------- | ----------------- | ------------------------------------------ |
| `None`               | unset             | `~/.mybot`                                 |
| `None`               | `play`            | `~/.mybot/workspaces/play`                 |
| `"work"`             | unset             | `~/.mybot/workspaces/work`                 |
| `"/tmp/sandbox"`     | unset             | `/tmp/sandbox` (resolved)                  |
| `"~/projects/foo"`   | unset             | `<HOME>/projects/foo`                      |
| `"./local"`          | unset             | `<CWD>/local` (resolved)                   |


<!-- @trace
source: initial-mybot-fork
updated: 2026-05-03
code:
  - CLAUDE.md
  - .spectra.yaml
-->

---
### Requirement: Process-wide active data dir

The function `set_active_data_dir(path)` SHALL store the given path as the process-wide active data dir. All helpers (`get_data_path`, `get_config_path`, `Config.workspace_path`) SHALL read from this stored value.

The CLI's main typer callback SHALL call `set_active_data_dir(resolve_data_dir(workspace))` exactly once per invocation, before any subcommand body runs.

#### Scenario: -w flag changes the active dir

- **WHEN** the user runs `mybot -w work status`
- **THEN** before `status` executes, the active data dir is `~/.mybot/workspaces/work/`
- **AND** `mybot status` reads `~/.mybot/workspaces/work/config.json` (not the default)


<!-- @trace
source: initial-mybot-fork
updated: 2026-05-03
code:
  - CLAUDE.md
  - .spectra.yaml
-->

---
### Requirement: Default workspace folder fallback

`Config.workspace_path` SHALL fall back to `<active_data_dir>/workspace` when `agents.defaults.workspace` is the empty string. When non-empty, the configured value SHALL be expanded (`~` → home) and used as-is.

#### Scenario: Empty config means default folder

- **GIVEN** `agents.defaults.workspace = ""`
- **AND** the active data dir is `~/.mybot/workspaces/work/`
- **WHEN** `Config.workspace_path` is read
- **THEN** the result is `~/.mybot/workspaces/work/workspace`

#### Scenario: Explicit folder overrides

- **GIVEN** `agents.defaults.workspace = "/Users/me/projects/repo"`
- **WHEN** `Config.workspace_path` is read
- **THEN** the result is `/Users/me/projects/repo` regardless of the active data dir

<!-- @trace
source: initial-mybot-fork
updated: 2026-05-03
code:
  - CLAUDE.md
  - .spectra.yaml
-->