## 1. Fork & rebrand

- [x] 1.1 Copy `nanobot/nanobot/` → `mybot/mybot/`, drop `bridge/`, `tests/`, `channels/`, `__pycache__/`
- [x] 1.2 Bulk replace `nanobot` → `mybot` (and `Nanobot`/`NANOBOT` casings) across `*.py`, `*.md`, `*.sh`
- [x] 1.3 Rebrand paths: `~/.nanobot/` → `~/.mybot/`, env prefix `NANOBOT_` → `MYBOT_`

## 2. Strip channels

- [x] 2.1 Delete `mybot/channels/` directory
- [x] 2.2 Rewrite `mybot/config/schema.py` removing `ChannelsConfig`, `WhatsAppConfig`, `TelegramConfig`, `FeishuConfig`, `DingTalkConfig`, `DiscordConfig`, `MatrixConfig` (×2), `EmailConfig`, `MochatConfig`, `SlackConfig`, `QQConfig`, `SlackDMConfig`, `MochatMentionConfig`, `MochatGroupRule`, plus the `channels` field on `Config`
- [x] 2.3 Drop `gateway`, `channels` typer commands and `_get_bridge_dir` from `cli/commands.py`
- [x] 2.4 Drop `channels_config` parameter on `AgentLoop` (kept `channel:chat_id` plumbing string everywhere else)
- [x] 2.5 Simplify `MessageTool` schema (remove `channel`/`chat_id` from public params; internal `set_context` keeps them)
- [x] 2.6 Trim `pyproject.toml` deps: drop `python-telegram-bot[socks]`, `slack-sdk`, `slackify-markdown`, `lark-oapi`, `qq-botpy`, `dingtalk-stream`, `python-socketio`, `msgpack`, `python-socks[asyncio]`, `socksio`, `websockets`, `websocket-client`; drop `matrix` extras; drop `bridge` force-include

## 3. Workspace resolution

- [x] 3.1 Add `resolve_data_dir`, `set_active_data_dir`, `list_named_workspaces`, module-level `_ACTIVE_DATA_DIR` to `utils/helpers.py`
- [x] 3.2 Make `get_config_path()` resolve via active data dir
- [x] 3.3 Default `agents.defaults.workspace = ""` and have `Config.workspace_path` fall back to `<data_dir>/workspace`
- [x] 3.4 Add global `--workspace`/`-w` option on the typer callback that calls `set_active_data_dir(resolve_data_dir(workspace))`
- [x] 3.5 Make `MYBOT_WORKSPACE` env var the default for `--workspace`

## 4. Bot management commands

- [x] 4.1 Add `mybot create [bot_name] [--folder PATH]` that calls `_do_onboard` and persists `--folder` into `agents.defaults.workspace`
- [x] 4.2 Add `mybot list` showing default + named bots, with **Data Dir**, **Workspace Folder**, **Active** columns
- [x] 4.3 Add `mybot delete <bot_name> [-y]` that `shutil.rmtree`s `~/.mybot/workspaces/<name>/` (data dir only — not user-supplied folders)
- [x] 4.4 Add `mybot <bot_name> set-folder <path>` to change workspace folder on an existing bot; `set-folder -` resets to default
- [x] 4.5 Keep `mybot onboard` as hidden alias for back-compat

## 5. Chat shortcut

- [x] 5.1 Define `RESERVED_COMMANDS` set (`create`, `delete`, `list`, `agent`, `cron`, `status`, `workspace`, `provider`, `onboard`, `set-folder`)
- [x] 5.2 Implement `_parse_chat_shortcut(argv)` that rewrites `mybot <name> [msg…]` → `mybot -w <name> agent [-m "<joined>"]`
- [x] 5.3 Handle chained subcommands: `mybot <name> <reserved> ...` → `mybot -w <name> <reserved> ...`
- [x] 5.4 Bail out when first token starts with `-` (so `mybot --help` / `mybot --version` / `mybot -w foo …` still go straight to typer)
- [x] 5.5 Add `run()` entry point and update `pyproject.toml` `[project.scripts]` and `__main__.py` to use it

## 6. Verification

- [x] 6.1 `python -c "import mybot"` succeeds
- [x] 6.2 `mybot --help` lists all commands
- [x] 6.3 `mybot create work --folder ~/projects/test` writes config, creates workspace, and config persists `agents.defaults.workspace`
- [x] 6.4 `mybot work cron add/list/remove` works and is isolated from other bots
- [x] 6.5 `mybot work "hello"` triggers chat shortcut (errors on missing API key, proving rewrite works)
- [x] 6.6 `mybot list` shows correct Data Dir + Workspace Folder per bot
- [x] 6.7 `mybot work set-folder ~/Desktop` updates config; `set-folder -` resets

## 7. Documentation & repo

- [x] 7.1 Write `README.md` (quick start, bot management, workspace folders, CLI reference, project layout, what was removed, roadmap)
- [x] 7.2 Add `.gitignore` (`.venv/`, `__pycache__/`, build, IDE, OS junk)
- [x] 7.3 Initial commit on `main` (specific file paths — no `-A`)
- [x] 7.4 Push `main` to `git@github.com:yiting-tom/mybot.git`

## 8. Spectra archival (this change)

- [x] 8.1 `spectra init --tools claude`
- [x] 8.2 `spectra new change initial-mybot-fork`
- [x] 8.3 Author `proposal.md`, `design.md`, `tasks.md`
- [ ] 8.4 `spectra validate initial-mybot-fork` and address any gaps
- [ ] 8.5 `spectra archive initial-mybot-fork` once validated
