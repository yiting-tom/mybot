"""CLI commands for mybot."""

import asyncio
import os
import select
import signal
import sys
from pathlib import Path

import typer
from prompt_toolkit import PromptSession
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.history import FileHistory
from prompt_toolkit.patch_stdout import patch_stdout
from rich.console import Console
from rich.markdown import Markdown
from rich.table import Table
from rich.text import Text

from mybot import __logo__, __version__
from mybot.config.schema import Config
from mybot.utils.helpers import sync_workspace_templates

app = typer.Typer(
    name="mybot",
    help=(
        f"{__logo__} mybot - Personal AI Assistant\n\n"
        "Chat with a bot:  mybot <bot_name> [message]\n"
        "Create a bot:     mybot create <bot_name>\n"
        "List bots:        mybot list\n"
        "Delete a bot:     mybot delete <bot_name>"
    ),
    no_args_is_help=True,
)

# Top-level command names that are NOT bot names. Used by the entry-point
# wrapper (`run`) to decide whether `mybot foo` means a subcommand or a chat
# shortcut for bot "foo".
RESERVED_COMMANDS = {
    "create", "delete", "list", "agent", "cron", "status",
    "workspace", "provider", "onboard", "set-folder", "daemon",
}

console = Console()
EXIT_COMMANDS = {"exit", "quit", "/exit", "/quit", ":q"}

# ---------------------------------------------------------------------------
# CLI input: prompt_toolkit for editing, paste, history, and display
# ---------------------------------------------------------------------------

_PROMPT_SESSION: PromptSession | None = None
_SAVED_TERM_ATTRS = None  # original termios settings, restored on exit


def _flush_pending_tty_input() -> None:
    """Drop unread keypresses typed while the model was generating output."""
    try:
        fd = sys.stdin.fileno()
        if not os.isatty(fd):
            return
    except Exception:
        return

    try:
        import termios
        termios.tcflush(fd, termios.TCIFLUSH)
        return
    except Exception:
        pass

    try:
        while True:
            ready, _, _ = select.select([fd], [], [], 0)
            if not ready:
                break
            if not os.read(fd, 4096):
                break
    except Exception:
        return


def _restore_terminal() -> None:
    """Restore terminal to its original state (echo, line buffering, etc.)."""
    if _SAVED_TERM_ATTRS is None:
        return
    try:
        import termios
        termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, _SAVED_TERM_ATTRS)
    except Exception:
        pass


def _init_prompt_session() -> None:
    """Create the prompt_toolkit session with persistent file history."""
    global _PROMPT_SESSION, _SAVED_TERM_ATTRS

    try:
        import termios
        _SAVED_TERM_ATTRS = termios.tcgetattr(sys.stdin.fileno())
    except Exception:
        pass

    from mybot.utils.helpers import get_data_path
    history_file = get_data_path() / "history" / "cli_history"
    history_file.parent.mkdir(parents=True, exist_ok=True)

    _PROMPT_SESSION = PromptSession(
        history=FileHistory(str(history_file)),
        enable_open_in_editor=False,
        multiline=False,
    )


def _print_agent_response(response: str, render_markdown: bool) -> None:
    """Render assistant response with consistent terminal styling."""
    content = response or ""
    body = Markdown(content) if render_markdown else Text(content)
    console.print()
    console.print(f"[cyan]{__logo__} mybot[/cyan]")
    console.print(body)
    console.print()


def _is_exit_command(command: str) -> bool:
    return command.lower() in EXIT_COMMANDS


async def _read_interactive_input_async() -> str:
    if _PROMPT_SESSION is None:
        raise RuntimeError("Call _init_prompt_session() first")
    try:
        with patch_stdout():
            return await _PROMPT_SESSION.prompt_async(
                HTML("<b fg='ansiblue'>You:</b> "),
            )
    except EOFError as exc:
        raise KeyboardInterrupt from exc



def version_callback(value: bool):
    if value:
        console.print(f"{__logo__} mybot v{__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        None, "--version", callback=version_callback, is_eager=True
    ),
    workspace: str = typer.Option(
        None, "--workspace", "-w",
        help="Workspace name (under ~/.mybot/workspaces/) or path. Env: MYBOT_WORKSPACE.",
    ),
):
    """mybot - Personal AI Assistant.

    Each workspace is an isolated bundle of config, sessions, cron jobs, and the
    agent's working directory. Use `-w NAME` for a named workspace under
    ~/.mybot/workspaces/, or `-w /path/to/dir` for an explicit location.
    Defaults to ~/.mybot when nothing is set.
    """
    from mybot.utils.helpers import resolve_data_dir, set_active_data_dir
    set_active_data_dir(resolve_data_dir(workspace))


# ============================================================================
# Bot management (create / list / delete)
# ============================================================================


def _do_onboard(folder: str | None = None):
    """Shared body for `mybot create` and the legacy `mybot onboard`.

    If `folder` is given, persist it as the bot's agent workspace path so the
    agent reads/writes files there instead of the default <data_dir>/workspace.
    """
    from mybot.config.loader import get_config_path, load_config, save_config
    from mybot.config.schema import Config

    config_path = get_config_path()
    fresh = not config_path.exists()

    if fresh:
        config = Config()
    else:
        console.print(f"[yellow]Bot already exists at {config_path.parent}[/yellow]")
        console.print("  [bold]y[/bold] = overwrite with defaults (existing values will be lost)")
        console.print("  [bold]N[/bold] = refresh config, keeping existing values and adding new fields")
        config = Config() if typer.confirm("Overwrite?") else load_config()

    if folder is not None:
        resolved = str(Path(folder).expanduser().resolve())
        config.agents.defaults.workspace = resolved

    save_config(config)
    if fresh:
        console.print(f"[green]✓[/green] Created config at {config_path}")
    else:
        console.print(f"[green]✓[/green] Config saved at {config_path}")

    # Resolve the workspace via the saved config so the override is honored.
    workspace = config.workspace_path
    workspace.mkdir(parents=True, exist_ok=True)
    console.print(f"[green]✓[/green] Workspace folder: {workspace}")
    sync_workspace_templates(workspace)
    return config_path, workspace


@app.command("create")
def create(
    bot_name: str = typer.Argument(None, help="Bot name. Omit for the default bot."),
    folder: str = typer.Option(
        None, "--folder", "-f",
        help="Agent's workspace folder (where memory, skills, HEARTBEAT.md live). "
             "Defaults to <data_dir>/workspace.",
    ),
):
    """Create a new bot (or refresh an existing one)."""
    from mybot.utils.helpers import resolve_data_dir, set_active_data_dir

    if bot_name:
        set_active_data_dir(resolve_data_dir(bot_name))

    config_path, _ = _do_onboard(folder=folder)
    chat_hint = f"mybot {bot_name}" if bot_name else "mybot"
    console.print(f"\n{__logo__} mybot is ready!")
    console.print("\nNext steps:")
    console.print(f"  1. Add your API key to [cyan]{config_path}[/cyan]")
    console.print("     Get one at: https://openrouter.ai/keys")
    console.print(f"  2. Chat: [cyan]{chat_hint}[/cyan]")


@app.command("list")
def list_bots():
    """List all bots (the default bot plus any named ones)."""
    from mybot.config.loader import load_config
    from mybot.utils.helpers import (
        DEFAULT_DATA_DIR,
        get_data_path,
        list_named_workspaces,
        set_active_data_dir,
    )

    active = get_data_path()
    names = list_named_workspaces()

    table = Table(title="Bots")
    table.add_column("Name", style="cyan")
    table.add_column("Data Dir")
    table.add_column("Workspace Folder")
    table.add_column("Active")

    def _folder_for(data_dir: Path) -> str:
        cfg = data_dir / "config.json"
        if not cfg.exists():
            return "[dim](not created)[/dim]"
        prev_active = get_data_path()
        try:
            set_active_data_dir(data_dir)
            return str(load_config(cfg).workspace_path)
        finally:
            set_active_data_dir(prev_active)

    table.add_row(
        "(default)", str(DEFAULT_DATA_DIR),
        _folder_for(DEFAULT_DATA_DIR),
        "✓" if active == DEFAULT_DATA_DIR else "",
    )
    for name in names:
        path = DEFAULT_DATA_DIR / "workspaces" / name
        table.add_row(name, str(path), _folder_for(path), "✓" if active == path else "")

    console.print(table)
    if not names:
        console.print("\n[dim]No named bots yet. Create one with:[/dim]")
        console.print("  [cyan]mybot create <bot_name>[/cyan]")
        console.print("  [cyan]mybot create <bot_name> --folder /path/to/dir[/cyan]")


@app.command("delete")
def delete_bot(
    bot_name: str = typer.Argument(..., help="Bot name to delete"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
):
    """Delete a named bot's data directory (config, sessions, cron, history)."""
    import shutil

    from mybot.utils.helpers import DEFAULT_DATA_DIR

    target = DEFAULT_DATA_DIR / "workspaces" / bot_name
    if not target.exists():
        console.print(f"[red]Bot '{bot_name}' not found at {target}[/red]")
        raise typer.Exit(1)

    if not yes:
        console.print(f"[yellow]This will permanently delete {target}[/yellow]")
        if not typer.confirm("Continue?"):
            console.print("Cancelled.")
            raise typer.Exit()

    shutil.rmtree(target)
    console.print(f"[green]✓[/green] Deleted bot '{bot_name}'")


# Legacy: keep `mybot onboard` working for users who used it before.
@app.command("onboard", hidden=True)
def onboard_legacy(
    folder: str = typer.Option(None, "--folder", "-f"),
):
    """Initialize current workspace (legacy; use `mybot create <name>`)."""
    config_path, _ = _do_onboard(folder=folder)
    console.print(f"\n{__logo__} mybot is ready!")
    console.print(f"  1. Add your API key to [cyan]{config_path}[/cyan]")
    console.print("  2. Chat: [cyan]mybot[/cyan]")


@app.command("set-folder")
def set_folder(
    folder: str = typer.Argument(..., help="New agent workspace folder, or '-' to reset to default"),
):
    """Change the active bot's agent workspace folder."""
    from mybot.config.loader import get_config_path, load_config, save_config

    config_path = get_config_path()
    if not config_path.exists():
        console.print(f"[red]No bot at {config_path.parent}. Run `mybot create` first.[/red]")
        raise typer.Exit(1)

    config = load_config()
    if folder == "-":
        config.agents.defaults.workspace = ""
        save_config(config)
        console.print(f"[green]✓[/green] Workspace folder reset to default: {config.workspace_path}")
        return

    resolved = str(Path(folder).expanduser().resolve())
    config.agents.defaults.workspace = resolved
    save_config(config)
    target = config.workspace_path
    target.mkdir(parents=True, exist_ok=True)
    sync_workspace_templates(target)
    console.print(f"[green]✓[/green] Workspace folder set to: {target}")




def _make_provider(config: Config):
    """Create the appropriate LLM provider from config."""
    from mybot.providers.custom_provider import CustomProvider
    from mybot.providers.litellm_provider import LiteLLMProvider
    from mybot.providers.openai_codex_provider import OpenAICodexProvider

    model = config.agents.defaults.model
    provider_name = config.get_provider_name(model)
    p = config.get_provider(model)

    if provider_name == "openai_codex" or model.startswith("openai-codex/"):
        return OpenAICodexProvider(default_model=model)

    if provider_name == "custom":
        return CustomProvider(
            api_key=p.api_key if p else "no-key",
            api_base=config.get_api_base(model) or "http://localhost:8000/v1",
            default_model=model,
        )

    from mybot.providers.registry import find_by_name
    spec = find_by_name(provider_name)
    if not model.startswith("bedrock/") and not (p and p.api_key) and not (spec and spec.is_oauth):
        from mybot.config.loader import get_config_path
        console.print("[red]Error: No API key configured.[/red]")
        console.print(f"Set one in {get_config_path()} under providers section")
        raise typer.Exit(1)

    return LiteLLMProvider(
        api_key=p.api_key if p else None,
        api_base=config.get_api_base(model),
        default_model=model,
        extra_headers=p.extra_headers if p else None,
        provider_name=provider_name,
    )


# ============================================================================
# Agent Commands
# ============================================================================


@app.command()
def agent(
    message: str = typer.Option(None, "--message", "-m", help="Message to send to the agent"),
    session_id: str = typer.Option("cli:direct", "--session", "-s", help="Session ID"),
    markdown: bool = typer.Option(True, "--markdown/--no-markdown", help="Render assistant output as Markdown"),
    logs: bool = typer.Option(False, "--logs/--no-logs", help="Show mybot runtime logs during chat"),
):
    """Interact with the agent directly."""
    from loguru import logger

    from mybot.agent.loop import AgentLoop
    from mybot.bus.queue import MessageBus
    from mybot.config.loader import get_data_dir, load_config
    from mybot.cron.service import CronService

    config = load_config()
    sync_workspace_templates(config.workspace_path)

    bus = MessageBus()
    provider = _make_provider(config)

    cron_store_path = get_data_dir() / "cron" / "jobs.json"
    cron = CronService(cron_store_path)

    if logs:
        logger.enable("mybot")
    else:
        logger.disable("mybot")

    agent_loop = AgentLoop(
        bus=bus,
        provider=provider,
        workspace=config.workspace_path,
        model=config.agents.defaults.model,
        temperature=config.agents.defaults.temperature,
        max_tokens=config.agents.defaults.max_tokens,
        max_iterations=config.agents.defaults.max_tool_iterations,
        memory_window=config.agents.defaults.memory_window,
        reasoning_effort=config.agents.defaults.reasoning_effort,
        brave_api_key=config.tools.web.search.api_key or None,
        web_proxy=config.tools.web.proxy or None,
        exec_config=config.tools.exec,
        cron_service=cron,
        restrict_to_workspace=config.tools.restrict_to_workspace,
        mcp_servers=config.tools.mcp_servers,
    )

    def _thinking_ctx():
        if logs:
            from contextlib import nullcontext
            return nullcontext()
        return console.status("[dim]mybot is thinking...[/dim]", spinner="dots")

    async def _cli_progress(content: str, *, tool_hint: bool = False) -> None:
        console.print(f"  [dim]↳ {content}[/dim]")

    if message:
        async def run_once():
            with _thinking_ctx():
                response = await agent_loop.process_direct(message, session_id, on_progress=_cli_progress)
            _print_agent_response(response, render_markdown=markdown)
            await agent_loop.close_mcp()

        asyncio.run(run_once())
    else:
        from mybot.bus.events import InboundMessage
        _init_prompt_session()
        console.print(f"{__logo__} Interactive mode (type [bold]exit[/bold] or [bold]Ctrl+C[/bold] to quit)\n")

        if ":" in session_id:
            cli_channel, cli_chat_id = session_id.split(":", 1)
        else:
            cli_channel, cli_chat_id = "cli", session_id

        def _exit_on_sigint(signum, frame):
            _restore_terminal()
            console.print("\nGoodbye!")
            os._exit(0)

        signal.signal(signal.SIGINT, _exit_on_sigint)

        async def run_interactive():
            bus_task = asyncio.create_task(agent_loop.run())
            turn_done = asyncio.Event()
            turn_done.set()
            turn_response: list[str] = []

            async def _consume_outbound():
                while True:
                    try:
                        msg = await asyncio.wait_for(bus.consume_outbound(), timeout=1.0)
                        if msg.metadata.get("_progress"):
                            console.print(f"  [dim]↳ {msg.content}[/dim]")
                        elif not turn_done.is_set():
                            if msg.content:
                                turn_response.append(msg.content)
                            turn_done.set()
                        elif msg.content:
                            console.print()
                            _print_agent_response(msg.content, render_markdown=markdown)
                    except asyncio.TimeoutError:
                        continue
                    except asyncio.CancelledError:
                        break

            outbound_task = asyncio.create_task(_consume_outbound())

            try:
                while True:
                    try:
                        _flush_pending_tty_input()
                        user_input = await _read_interactive_input_async()
                        command = user_input.strip()
                        if not command:
                            continue

                        if _is_exit_command(command):
                            _restore_terminal()
                            console.print("\nGoodbye!")
                            break

                        turn_done.clear()
                        turn_response.clear()

                        await bus.publish_inbound(InboundMessage(
                            channel=cli_channel,
                            sender_id="user",
                            chat_id=cli_chat_id,
                            content=user_input,
                        ))

                        with _thinking_ctx():
                            await turn_done.wait()

                        if turn_response:
                            _print_agent_response(turn_response[0], render_markdown=markdown)
                    except KeyboardInterrupt:
                        _restore_terminal()
                        console.print("\nGoodbye!")
                        break
                    except EOFError:
                        _restore_terminal()
                        console.print("\nGoodbye!")
                        break
            finally:
                agent_loop.stop()
                outbound_task.cancel()
                await asyncio.gather(bus_task, outbound_task, return_exceptions=True)
                await agent_loop.close_mcp()

        asyncio.run(run_interactive())


# ============================================================================
# Cron Commands
# ============================================================================

cron_app = typer.Typer(help="Manage scheduled tasks")
app.add_typer(cron_app, name="cron")


@cron_app.command("list")
def cron_list(
    all: bool = typer.Option(False, "--all", "-a", help="Include disabled jobs"),
):
    """List scheduled jobs."""
    from mybot.config.loader import get_data_dir
    from mybot.cron.service import CronService

    store_path = get_data_dir() / "cron" / "jobs.json"
    service = CronService(store_path)

    jobs = service.list_jobs(include_disabled=all)

    if not jobs:
        console.print("No scheduled jobs.")
        return

    table = Table(title="Scheduled Jobs")
    table.add_column("ID", style="cyan")
    table.add_column("Name")
    table.add_column("Schedule")
    table.add_column("Status")
    table.add_column("Next Run")

    import time
    from datetime import datetime as _dt
    from zoneinfo import ZoneInfo
    for job in jobs:
        if job.schedule.kind == "every":
            sched = f"every {(job.schedule.every_ms or 0) // 1000}s"
        elif job.schedule.kind == "cron":
            sched = f"{job.schedule.expr or ''} ({job.schedule.tz})" if job.schedule.tz else (job.schedule.expr or "")
        else:
            sched = "one-time"

        next_run = ""
        if job.state.next_run_at_ms:
            ts = job.state.next_run_at_ms / 1000
            try:
                tz = ZoneInfo(job.schedule.tz) if job.schedule.tz else None
                next_run = _dt.fromtimestamp(ts, tz).strftime("%Y-%m-%d %H:%M")
            except Exception:
                next_run = time.strftime("%Y-%m-%d %H:%M", time.localtime(ts))

        status = "[green]enabled[/green]" if job.enabled else "[dim]disabled[/dim]"

        table.add_row(job.id, job.name, sched, status, next_run)

    console.print(table)


@cron_app.command("add")
def cron_add(
    name: str = typer.Option(..., "--name", "-n", help="Job name"),
    message: str = typer.Option(..., "--message", "-m", help="Message for agent"),
    every: int = typer.Option(None, "--every", "-e", help="Run every N seconds"),
    cron_expr: str = typer.Option(None, "--cron", "-c", help="Cron expression (e.g. '0 9 * * *')"),
    tz: str | None = typer.Option(None, "--tz", help="IANA timezone for cron (e.g. 'America/Vancouver')"),
    at: str = typer.Option(None, "--at", help="Run once at time (ISO format)"),
):
    """Add a scheduled job."""
    from mybot.config.loader import get_data_dir
    from mybot.cron.service import CronService
    from mybot.cron.types import CronSchedule

    if tz and not cron_expr:
        console.print("[red]Error: --tz can only be used with --cron[/red]")
        raise typer.Exit(1)

    if every:
        schedule = CronSchedule(kind="every", every_ms=every * 1000)
    elif cron_expr:
        schedule = CronSchedule(kind="cron", expr=cron_expr, tz=tz)
    elif at:
        import datetime
        dt = datetime.datetime.fromisoformat(at)
        schedule = CronSchedule(kind="at", at_ms=int(dt.timestamp() * 1000))
    else:
        console.print("[red]Error: Must specify --every, --cron, or --at[/red]")
        raise typer.Exit(1)

    store_path = get_data_dir() / "cron" / "jobs.json"
    service = CronService(store_path)

    try:
        job = service.add_job(
            name=name,
            schedule=schedule,
            message=message,
        )
    except ValueError as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1) from e

    console.print(f"[green]✓[/green] Added job '{job.name}' ({job.id})")


@cron_app.command("remove")
def cron_remove(
    job_id: str = typer.Argument(..., help="Job ID to remove"),
):
    """Remove a scheduled job."""
    from mybot.config.loader import get_data_dir
    from mybot.cron.service import CronService

    store_path = get_data_dir() / "cron" / "jobs.json"
    service = CronService(store_path)

    if service.remove_job(job_id):
        console.print(f"[green]✓[/green] Removed job {job_id}")
    else:
        console.print(f"[red]Job {job_id} not found[/red]")


@cron_app.command("enable")
def cron_enable(
    job_id: str = typer.Argument(..., help="Job ID"),
    disable: bool = typer.Option(False, "--disable", help="Disable instead of enable"),
):
    """Enable or disable a job."""
    from mybot.config.loader import get_data_dir
    from mybot.cron.service import CronService

    store_path = get_data_dir() / "cron" / "jobs.json"
    service = CronService(store_path)

    job = service.enable_job(job_id, enabled=not disable)
    if job:
        status = "disabled" if disable else "enabled"
        console.print(f"[green]✓[/green] Job '{job.name}' {status}")
    else:
        console.print(f"[red]Job {job_id} not found[/red]")


@cron_app.command("run")
def cron_run(
    job_id: str = typer.Argument(..., help="Job ID to run"),
    force: bool = typer.Option(False, "--force", "-f", help="Run even if disabled"),
):
    """Manually run a job."""
    from loguru import logger

    from mybot.agent.loop import AgentLoop
    from mybot.bus.queue import MessageBus
    from mybot.config.loader import get_data_dir, load_config
    from mybot.cron.service import CronService
    from mybot.cron.types import CronJob
    logger.disable("mybot")

    config = load_config()
    provider = _make_provider(config)
    bus = MessageBus()
    agent_loop = AgentLoop(
        bus=bus,
        provider=provider,
        workspace=config.workspace_path,
        model=config.agents.defaults.model,
        temperature=config.agents.defaults.temperature,
        max_tokens=config.agents.defaults.max_tokens,
        max_iterations=config.agents.defaults.max_tool_iterations,
        memory_window=config.agents.defaults.memory_window,
        reasoning_effort=config.agents.defaults.reasoning_effort,
        brave_api_key=config.tools.web.search.api_key or None,
        web_proxy=config.tools.web.proxy or None,
        exec_config=config.tools.exec,
        restrict_to_workspace=config.tools.restrict_to_workspace,
        mcp_servers=config.tools.mcp_servers,
    )

    store_path = get_data_dir() / "cron" / "jobs.json"
    service = CronService(store_path)

    result_holder = []

    async def on_job(job: CronJob) -> str | None:
        response = await agent_loop.process_direct(
            job.payload.message,
            session_key=f"cron:{job.id}",
            channel="cli",
            chat_id="direct",
        )
        result_holder.append(response)
        return response

    service.on_job = on_job

    async def run():
        return await service.run_job(job_id, force=force)

    if asyncio.run(run()):
        console.print("[green]✓[/green] Job executed")
        if result_holder:
            _print_agent_response(result_holder[0], render_markdown=True)
    else:
        console.print(f"[red]Failed to run job {job_id}[/red]")


# ============================================================================
# Daemon Command
# ============================================================================


def _daemon_emit(out: Console, source: str, content: str, *, dim: bool = False) -> None:
    """Emit one timestamped line: `<YYYY-MM-DD HH:MM:SS> [<source>] <content>`."""
    from datetime import datetime
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    body = f"  ↳ {content}" if dim else content
    line = f"{ts} [{source}]  {body}"
    out.print(f"[dim]{line}[/dim]" if dim else line)


def _acquire_lockfile(data_dir: Path, bot_label: str) -> Path:
    """Write our PID to <data_dir>/daemon.pid; refuse if a live PID owns it."""
    lockfile = data_dir / "daemon.pid"
    if lockfile.exists():
        try:
            existing_pid = int(lockfile.read_text().strip())
        except (ValueError, OSError):
            existing_pid = 0
        if existing_pid > 0:
            try:
                os.kill(existing_pid, 0)  # 0 = probe, doesn't deliver a signal
                console.print(
                    f"[red]Daemon already running for '{bot_label}' (pid {existing_pid})[/red]"
                )
                raise typer.Exit(1)
            except ProcessLookupError:
                # Stale lockfile — overwrite below.
                pass
            except PermissionError:
                # PID exists but is owned by another user; treat as live.
                console.print(
                    f"[red]Daemon already running for '{bot_label}' (pid {existing_pid})[/red]"
                )
                raise typer.Exit(1) from None

    lockfile.parent.mkdir(parents=True, exist_ok=True)
    lockfile.write_text(str(os.getpid()))
    return lockfile


@app.command("daemon")
def daemon(
    once: bool = typer.Option(False, "--once", "-1", help="Run every currently-due cron job and exit (skips heartbeat)."),
    log_file: str = typer.Option(None, "--log-file", "-l", help="Mirror stdout to this file."),
):
    """Run cron + heartbeat for the active bot in the foreground."""
    from loguru import logger

    from mybot.agent.loop import AgentLoop
    from mybot.bus.queue import MessageBus
    from mybot.config.loader import get_data_dir, load_config
    from mybot.cron.service import CronService
    from mybot.cron.types import CronJob
    from mybot.heartbeat.service import HeartbeatService
    from mybot.session.manager import SessionManager
    from mybot.utils.helpers import DEFAULT_DATA_DIR

    data_dir = get_data_dir()
    bot_label = (
        "(default)" if data_dir == DEFAULT_DATA_DIR
        else data_dir.name if data_dir.parent == DEFAULT_DATA_DIR / "workspaces"
        else str(data_dir)
    )

    config = load_config()
    sync_workspace_templates(config.workspace_path, silent=True)

    # Output sink: stdout + optional tee to log file.
    if log_file:
        log_path = Path(log_file).expanduser()
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_fp = open(log_path, "a", encoding="utf-8", buffering=1)  # line-buffered
        out = Console(file=_TeeFile(sys.stdout, log_fp), force_terminal=sys.stdout.isatty())
    else:
        log_fp = None
        out = console

    # Preflight: provider must be constructible (catches missing API key).
    provider = _make_provider(config)

    # Diagnostic logs are still loguru-gated; daemon output uses Rich directly.
    logger.disable("mybot")

    if once:
        asyncio.run(_run_daemon_once(config, provider, out))
        if log_fp:
            log_fp.close()
        return

    lockfile = _acquire_lockfile(data_dir, bot_label)

    bus = MessageBus()
    session_manager = SessionManager(config.workspace_path)
    cron_store_path = get_data_dir() / "cron" / "jobs.json"
    cron = CronService(cron_store_path)

    agent = AgentLoop(
        bus=bus,
        provider=provider,
        workspace=config.workspace_path,
        model=config.agents.defaults.model,
        temperature=config.agents.defaults.temperature,
        max_tokens=config.agents.defaults.max_tokens,
        max_iterations=config.agents.defaults.max_tool_iterations,
        memory_window=config.agents.defaults.memory_window,
        reasoning_effort=config.agents.defaults.reasoning_effort,
        brave_api_key=config.tools.web.search.api_key or None,
        web_proxy=config.tools.web.proxy or None,
        exec_config=config.tools.exec,
        cron_service=cron,
        restrict_to_workspace=config.tools.restrict_to_workspace,
        session_manager=session_manager,
        mcp_servers=config.tools.mcp_servers,
    )

    async def on_cron_job(job: CronJob) -> str | None:
        source = f"cron:{job.id}"

        async def _progress(content: str, *, tool_hint: bool = False) -> None:
            _daemon_emit(out, source, content, dim=True)

        reminder = (
            "[Scheduled Task] Timer finished.\n\n"
            f"Task '{job.name}' has been triggered.\n"
            f"Scheduled instruction: {job.payload.message}"
        )
        response = await agent.process_direct(
            reminder,
            session_key=f"cron:{job.id}",
            channel="cli",
            chat_id="direct",
            on_progress=_progress,
        )
        if response:
            _daemon_emit(out, source, response)
        return response

    cron.on_job = on_cron_job

    async def on_heartbeat_execute(tasks: str) -> str:
        async def _progress(content: str, *, tool_hint: bool = False) -> None:
            _daemon_emit(out, "heartbeat", content, dim=True)

        return await agent.process_direct(
            tasks,
            session_key="heartbeat",
            channel="cli",
            chat_id="direct",
            on_progress=_progress,
        )

    async def on_heartbeat_notify(response: str) -> None:
        if response:
            _daemon_emit(out, "heartbeat", response)

    hb_cfg = config.gateway.heartbeat
    heartbeat = HeartbeatService(
        workspace=config.workspace_path,
        provider=provider,
        model=agent.model,
        on_execute=on_heartbeat_execute,
        on_notify=on_heartbeat_notify,
        interval_s=hb_cfg.interval_s,
        enabled=hb_cfg.enabled,
    )

    cron_count = cron.status()["jobs"]
    _daemon_emit(
        out, "daemon",
        f"Daemon started for bot '{bot_label}' (cron jobs: {cron_count}, heartbeat: every {hb_cfg.interval_s}s)",
    )

    asyncio.run(_run_daemon_forever(agent, cron, heartbeat, lockfile, out, log_fp))


async def _run_daemon_forever(agent, cron, heartbeat, lockfile: Path, out: Console, log_fp) -> None:
    """Main daemon coroutine: starts services, awaits SIGINT/SIGTERM, shuts down."""
    loop = asyncio.get_running_loop()
    shutdown = asyncio.Event()
    forced_exit = {"flag": False}

    def _on_signal(signame: str) -> None:
        if shutdown.is_set():
            forced_exit["flag"] = True
            os._exit(1)
        _daemon_emit(out, "daemon", f"Received {signame}, shutting down...")
        shutdown.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, _on_signal, sig.name)

    agent_task = asyncio.create_task(agent.run())

    try:
        await cron.start()
        await heartbeat.start()
        await shutdown.wait()
    finally:
        heartbeat.stop()
        cron.stop()
        agent.stop()

        try:
            await asyncio.wait_for(agent_task, timeout=30.0)
        except asyncio.TimeoutError:
            agent_task.cancel()
            try:
                await agent_task
            except (asyncio.CancelledError, Exception):
                pass

        try:
            await agent.close_mcp()
        except (RuntimeError, BaseExceptionGroup):
            pass  # MCP SDK cancel-scope cleanup is noisy but harmless

        try:
            lockfile.unlink(missing_ok=True)
        except OSError:
            pass

        if log_fp:
            log_fp.close()

        if not forced_exit["flag"]:
            _daemon_emit(out, "daemon", "Daemon stopped.")


async def _run_daemon_once(config: Config, provider, out: Console) -> None:
    """`--once` mode: run every cron job whose next_run_at_ms <= now, then exit."""
    from mybot.agent.loop import AgentLoop
    from mybot.bus.queue import MessageBus
    from mybot.config.loader import get_data_dir
    from mybot.cron.service import CronService, _now_ms, _compute_next_run
    from mybot.cron.types import CronJob

    bus = MessageBus()
    cron_store_path = get_data_dir() / "cron" / "jobs.json"
    cron = CronService(cron_store_path)

    agent = AgentLoop(
        bus=bus,
        provider=provider,
        workspace=config.workspace_path,
        model=config.agents.defaults.model,
        temperature=config.agents.defaults.temperature,
        max_tokens=config.agents.defaults.max_tokens,
        max_iterations=config.agents.defaults.max_tool_iterations,
        memory_window=config.agents.defaults.memory_window,
        reasoning_effort=config.agents.defaults.reasoning_effort,
        brave_api_key=config.tools.web.search.api_key or None,
        web_proxy=config.tools.web.proxy or None,
        exec_config=config.tools.exec,
        cron_service=cron,
        restrict_to_workspace=config.tools.restrict_to_workspace,
        mcp_servers=config.tools.mcp_servers,
    )

    store = cron._load_store()
    now = _now_ms()
    due = [j for j in store.jobs if j.enabled and j.state.next_run_at_ms and now >= j.state.next_run_at_ms]

    if not due:
        return

    async def run_one(job: CronJob) -> None:
        source = f"cron:{job.id}"

        async def _progress(content: str, *, tool_hint: bool = False) -> None:
            _daemon_emit(out, source, content, dim=True)

        reminder = (
            "[Scheduled Task] Timer finished.\n\n"
            f"Task '{job.name}' has been triggered.\n"
            f"Scheduled instruction: {job.payload.message}"
        )
        response = await agent.process_direct(
            reminder,
            session_key=f"cron:{job.id}",
            channel="cli",
            chat_id="direct",
            on_progress=_progress,
        )
        if response:
            _daemon_emit(out, source, response)
        # Advance state.
        job.state.last_run_at_ms = _now_ms()
        job.state.last_status = "ok"
        if job.schedule.kind == "at":
            if job.delete_after_run:
                store.jobs = [j for j in store.jobs if j.id != job.id]
            else:
                job.enabled = False
                job.state.next_run_at_ms = None
        else:
            job.state.next_run_at_ms = _compute_next_run(job.schedule, _now_ms())

    try:
        for job in due:
            await run_one(job)
        cron._save_store()
    finally:
        try:
            await agent.close_mcp()
        except (RuntimeError, BaseExceptionGroup):
            pass


class _TeeFile:
    """Tiny file-like object that writes to two streams (stdout + log file)."""

    def __init__(self, primary, secondary):
        self._primary = primary
        self._secondary = secondary

    def write(self, data):
        self._primary.write(data)
        self._secondary.write(data)
        return len(data)

    def flush(self):
        self._primary.flush()
        self._secondary.flush()

    def isatty(self):
        return self._primary.isatty()

    def fileno(self):
        return self._primary.fileno()


# ============================================================================
# Status Commands
# ============================================================================


@app.command()
def status():
    """Show mybot status."""
    from mybot.config.loader import get_config_path, load_config

    config_path = get_config_path()
    config = load_config()
    workspace = config.workspace_path

    console.print(f"{__logo__} mybot Status\n")

    console.print(f"Config: {config_path} {'[green]✓[/green]' if config_path.exists() else '[red]✗[/red]'}")
    console.print(f"Workspace: {workspace} {'[green]✓[/green]' if workspace.exists() else '[red]✗[/red]'}")

    if config_path.exists():
        from mybot.providers.registry import PROVIDERS

        console.print(f"Model: {config.agents.defaults.model}")

        for spec in PROVIDERS:
            p = getattr(config.providers, spec.name, None)
            if p is None:
                continue
            if spec.is_oauth:
                console.print(f"{spec.label}: [green]✓ (OAuth)[/green]")
            elif spec.is_local:
                if p.api_base:
                    console.print(f"{spec.label}: [green]✓ {p.api_base}[/green]")
                else:
                    console.print(f"{spec.label}: [dim]not set[/dim]")
            else:
                has_key = bool(p.api_key)
                console.print(f"{spec.label}: {'[green]✓[/green]' if has_key else '[dim]not set[/dim]'}")


# ============================================================================
# OAuth Login
# ============================================================================

provider_app = typer.Typer(help="Manage providers")
app.add_typer(provider_app, name="provider")


_LOGIN_HANDLERS: dict[str, callable] = {}


def _register_login(name: str):
    def decorator(fn):
        _LOGIN_HANDLERS[name] = fn
        return fn
    return decorator


@provider_app.command("login")
def provider_login(
    provider: str = typer.Argument(..., help="OAuth provider (e.g. 'openai-codex', 'github-copilot')"),
):
    """Authenticate with an OAuth provider."""
    from mybot.providers.registry import PROVIDERS

    key = provider.replace("-", "_")
    spec = next((s for s in PROVIDERS if s.name == key and s.is_oauth), None)
    if not spec:
        names = ", ".join(s.name.replace("_", "-") for s in PROVIDERS if s.is_oauth)
        console.print(f"[red]Unknown OAuth provider: {provider}[/red]  Supported: {names}")
        raise typer.Exit(1)

    handler = _LOGIN_HANDLERS.get(spec.name)
    if not handler:
        console.print(f"[red]Login not implemented for {spec.label}[/red]")
        raise typer.Exit(1)

    console.print(f"{__logo__} OAuth Login - {spec.label}\n")
    handler()


@_register_login("openai_codex")
def _login_openai_codex() -> None:
    try:
        from oauth_cli_kit import get_token, login_oauth_interactive
        token = None
        try:
            token = get_token()
        except Exception:
            pass
        if not (token and token.access):
            console.print("[cyan]Starting interactive OAuth login...[/cyan]\n")
            token = login_oauth_interactive(
                print_fn=lambda s: console.print(s),
                prompt_fn=lambda s: typer.prompt(s),
            )
        if not (token and token.access):
            console.print("[red]✗ Authentication failed[/red]")
            raise typer.Exit(1)
        console.print(f"[green]✓ Authenticated with OpenAI Codex[/green]  [dim]{token.account_id}[/dim]")
    except ImportError:
        console.print("[red]oauth_cli_kit not installed. Run: pip install oauth-cli-kit[/red]")
        raise typer.Exit(1)


@_register_login("github_copilot")
def _login_github_copilot() -> None:
    import asyncio

    console.print("[cyan]Starting GitHub Copilot device flow...[/cyan]\n")

    async def _trigger():
        from litellm import acompletion
        await acompletion(model="github_copilot/gpt-4o", messages=[{"role": "user", "content": "hi"}], max_tokens=1)

    try:
        asyncio.run(_trigger())
        console.print("[green]✓ Authenticated with GitHub Copilot[/green]")
    except Exception as e:
        console.print(f"[red]Authentication error: {e}[/red]")
        raise typer.Exit(1)


# ============================================================================
# Entry point: rewrite `mybot <bot_name> [message]` → `mybot -w <bot_name> agent [-m message]`
# ============================================================================


def _parse_chat_shortcut(argv: list[str]) -> list[str] | None:
    """Detect `mybot <bot_name> [message...]` and return rewritten argv.

    Returns None when the input is a normal subcommand invocation (let typer
    handle it).
    """
    if not argv:
        return None

    # If the user passed any leading flag (including `-w`), they're being
    # explicit — let typer dispatch normally and don't auto-rewrite.
    if argv[0].startswith("-"):
        return None

    candidate = argv[0]
    if candidate in RESERVED_COMMANDS:
        return None
    i = 0

    bot_name = candidate
    rest = argv[i + 1 :]
    pre = argv[:i]

    # If the next token is a reserved subcommand (e.g. `mybot work cron list`),
    # rewrite to `-w <bot_name> <subcommand...>` rather than a chat shortcut.
    if rest and rest[0] in RESERVED_COMMANDS:
        return pre + ["-w", bot_name, *rest]

    # Otherwise: chat shortcut. `mybot foo` → interactive, `mybot foo "..."` →
    # single-shot message.
    new_argv = pre + ["-w", bot_name, "agent"]
    if rest:
        message = " ".join(rest)
        new_argv += ["-m", message]
    return new_argv


def run() -> None:
    """Entry point used by the `mybot` console script.

    Adds the `mybot <bot_name> [message]` chat shortcut on top of the regular
    typer dispatch.
    """
    rewritten = _parse_chat_shortcut(sys.argv[1:])
    if rewritten is not None:
        sys.argv = [sys.argv[0], *rewritten]
    app()


if __name__ == "__main__":
    run()
