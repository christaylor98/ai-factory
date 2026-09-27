"""
Agent runs: one headless `claude -p` session with tools, streamed, steerable and cancellable.

    run = start_agent(AgentSpec(prompt="fix the failing test", model="sonnet", mcp_servers={...},
                                allowed_tools=["mcp__axt__read", ...], schema=ANSWER))
    for event in run.events():        # started · call · usage · tool_use · tool_result · steer_echo · result · end
        ...
    answer = run.wait()               # AgentResult, or raises AgentRunError / ToolPolicyError
    run.steer("also update the docs") # while it runs (spec.steerable)
    run.cancel()                      # kill the whole process tree

This is the second entry point beside run(): one model interaction, streamed (docs/ARCHITECTURE.md). It is not
an orchestrator. It starts one process, reports what the stream shows, and ends. The caller decides what to do
next. Which tools a caller allows is the caller's policy; this module only passes the lists on and, with
enforce_allowed, fails a run that used a tool outside them.

Lifted from axChat's comp_curate/curate_cc.py (2026-09-27), where it ran every axChat segment: the stream parser,
the stdin inbox for steering, the pipe drain that survives an escaped descendant, and the process-group kill.
"""
from __future__ import annotations

import codecs
import json
import os
import queue
import re
import select
import signal
import subprocess
import tempfile
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterator, Optional

from . import admission
from .config import Config
from .ledger import write_run_to_ledger
from .metrics import build_metrics
from .pricing import resolve_price
from .result import ProviderResponse

# `claude --model` takes an alias or a Claude model id; `local` is the same CLI pointed at an Anthropic-compatible
# server on this machine (llama-server's /v1/messages). Anything else is refused before a process starts.
CLAUDE_MODEL = re.compile(r"^(sonnet|opus|haiku|fable|opusplan|default)(\[1m\])?$|^claude-[a-z0-9][a-z0-9.\-]*(\[1m\])?$")
LOCAL_MODEL = "local"
DEFAULT_LOCAL_URL = "http://127.0.0.1:8089"
# Tools the CLI itself uses in any run (deferred-tool loading, the schema'd answer): never a policy violation.
HARNESS_TOOLS = {"ToolSearch", "StructuredOutput"}
TOOL_RESULT_PREVIEW_CHARS = 2000
STEER_WAIT_S = 60.0   # after a result, how long an unechoed steer may keep stdin open before we give up on it
DEATH_GRACE_S = 3.0   # after claude itself exits, how long to keep draining its pipes


def check_model(model: str) -> str:
    if model == LOCAL_MODEL:
        return model
    if not isinstance(model, str) or not CLAUDE_MODEL.match(model):
        raise ValueError(f"not a Claude model for `claude --model`: {model!r} "
                         "(use sonnet / opus / haiku / fable, a claude-* id, or local)")
    return model


def model_env(model: str, local_url: str = DEFAULT_LOCAL_URL, base: Optional[dict] = None) -> dict:
    """The environment a `claude -p` on `model` runs with: the caller's as it is (a user who runs claude on an API
    key keeps it); for `local`, the local server's endpoint and a dummy key, which also keeps the login unused."""
    env = dict(os.environ if base is None else base)
    if model == LOCAL_MODEL:
        for k in ("ANTHROPIC_AUTH_TOKEN", "CLAUDE_CODE_OAUTH_TOKEN"):
            env.pop(k, None)
        env.update(ANTHROPIC_BASE_URL=local_url, ANTHROPIC_API_KEY="local", CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC="1")
    return env


def cli_model(model: str) -> str:
    """What `--model` gets: the local server ignores the name, but the CLI wants a claude-* one."""
    return "claude-local" if model == LOCAL_MODEL else model


@dataclass
class AgentSpec:
    """One agent run. Tool lists are passed to the CLI as given: the caller owns the policy."""
    prompt: str
    model: str = "sonnet"
    system: str = ""
    schema: Optional[dict] = None           # --json-schema: the answer is the structured output
    tools: list[str] = field(default_factory=list)            # built-in tools; [] = none (--tools "")
    allowed_tools: list[str] = field(default_factory=list)
    disallowed_tools: list[str] = field(default_factory=list)
    mcp_servers: dict = field(default_factory=dict)           # {"name": {"type": "stdio", "command": ...}}
    add_dirs: list[str] = field(default_factory=list)
    setting_sources: Optional[str] = None   # e.g. "project": with the empty cwd, no user or project settings load
    enforce_allowed: bool = True            # fail a run that called a tool outside tools + allowed_tools
    steerable: bool = False                 # stream-json stdin: steer() works, and stdin stays open for it
    timeout_s: float = 600
    stream_path: Optional[str] = None       # every stream line, in full
    debug_path: Optional[str] = None        # --debug-file
    local_url: str = DEFAULT_LOCAL_URL      # for model="local"
    env: Optional[dict] = None              # base environment for the process (default: os.environ)
    tags: dict = field(default_factory=dict)   # recorded on the ledger row: who asked, for what


class AgentRunError(RuntimeError):
    """A run that produced no usable result. Carries what DID happen, so callers can record it: tool calls that
    already ran (their side effects are real), non-JSON output lines (where a plain-text CLI error lands), the
    stderr tail and the debug log path."""

    def __init__(self, message: str, tool_calls: list[dict], text_lines: list[str], stderr: str,
                 returncode, debug_file: Optional[str]):
        super().__init__(message)
        self.tool_calls, self.text_lines, self.stderr = tool_calls, text_lines, stderr
        self.returncode, self.debug_file = returncode, debug_file


class ToolPolicyError(RuntimeError):
    """The run called a tool outside the spec's tools and allowed_tools (enforce_allowed)."""

    def __init__(self, message: str, tools: list[str], result: "AgentResult"):
        super().__init__(message)
        self.tools, self.result = tools, result


def user_message(text: str, uid: str) -> str:
    """One `--input-format stream-json` line: a user message with our own uuid (echoed back with
    `--replay-user-messages` at the moment the CLI consumes it)."""
    return json.dumps({"type": "user", "uuid": uid,
                       "message": {"role": "user", "content": [{"type": "text", "text": text}]}}) + "\n"


class Inbox:
    """User messages for a running `claude -p`: steering a run mid-way.

    The CLI folds a message written to its stream-json stdin into the running turn at the next tool boundary, or,
    if the turn's last API call has already started, runs it as a further turn (a second `result`). Delivery is
    mechanical: a message is delivered when the stream echoes its uuid, never on the model's word. stdin stays
    open while any sent message is unechoed; otherwise it closes at a `result`, which ends the process."""

    def __init__(self):
        self._lock = threading.Lock()
        self._stdin = None
        self.closed = False
        self.calls = 0                   # tool calls the stream has shown so far this run
        self.sent: dict[str, int] = {}   # uuid -> tool calls when it was written
        self.echoed: dict[str, int] = {} # uuid -> tool calls before its echo: those ran before the model saw it
        self.on_echo: Callable[[str, int], None] | None = None
        self.held = False           # the caller paused the run: stdin stays open even when idle
        self.after_result = False   # a result came and nothing has been taken in since: the CLI waits on stdin

    def attach(self, stdin) -> None:
        with self._lock:
            self._stdin = stdin

    def send(self, uid: str, text: str) -> bool:
        """Write one message to the running process; False when there is none to take it (not started, finished)."""
        with self._lock:
            if self.closed or self._stdin is None:
                return False
            try:
                self._stdin.write(user_message(text, uid))
                self._stdin.flush()
            except (OSError, ValueError):   # the process is gone: the caller carries the message forward
                return False
            self.sent[uid] = self.calls
            return True

    def echo(self, uid: str) -> None:
        self.after_result = False
        if uid in self.sent and uid not in self.echoed:
            self.echoed[uid] = self.calls
            if self.on_echo:
                self.on_echo(uid, self.calls)

    def release(self) -> None:
        """The pause is over. If the run already ended its turn and nothing is on its way in, end it now."""
        self.held = False
        if self.after_result and not self.close(only_if_idle=True):
            self.close_later()

    def close_later(self) -> None:
        """A steer was written but may never be taken in: stop waiting for it after STEER_WAIT_S."""
        timer = threading.Timer(STEER_WAIT_S, self.close)
        timer.daemon = True
        timer.start()

    def outstanding(self) -> list[str]:
        return [u for u in self.sent if u not in self.echoed]

    def close(self, only_if_idle: bool = False) -> bool:
        """Close stdin (the CLI exits after its current turn). With only_if_idle, not while a sent message is
        unechoed: that one is about to run as a further turn."""
        with self._lock:
            if self.closed:
                return True
            if only_if_idle and (self.outstanding() or self.held):
                return False
            self.closed = True
            try:
                if self._stdin is not None:
                    self._stdin.close()
            except OSError:
                pass
            return True


def summarise_result(block: dict) -> dict:
    """What came back from one tool call: size, error flag, whether it was empty, and a preview."""
    content = block.get("content")
    if isinstance(content, list):
        text = "".join(c.get("text", "") for c in content if isinstance(c, dict))
    else:
        text = str(content or "")
    empty = False
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict) and parsed.get("total") == 0 and not parsed.get("edges"):
            empty = True  # a graph query that found nothing -- usually a guessed id
    except (json.JSONDecodeError, TypeError):
        pass
    return {
        "result_chars": len(text),
        "result_error": bool(block.get("is_error")) or '"error"' in text[:200],
        "result_empty": empty,
        "result_preview": text[:TOOL_RESULT_PREVIEW_CHARS],
    }


def merged_result(results: list[dict]) -> dict:
    """A run's answer from its results (several when a late steer ran as a further turn): the last one with a
    structured output (else the last), with `usage` summed over all of them -- each result's usage is its own
    turn's -- and `total_cost_usd` as reported last (the CLI's figure is cumulative)."""
    if len(results) == 1:
        return results[0]
    answer = next((r for r in reversed(results) if r.get("structured_output")), results[-1])
    usage: dict = {}
    for r in results:
        for k, v in (r.get("usage") or {}).items():
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                usage[k] = usage.get(k, 0) + v
    return {**answer, "usage": usage, "total_cost_usd": results[-1].get("total_cost_usd"),
            "num_turns": sum(r.get("num_turns") or 0 for r in results), "results": len(results)}


class StreamParser:
    """Accumulates a `claude -p --output-format stream-json` stream: tool calls (paired with their results) and
    the final result message, and reports each as an event through `emit(event)` the moment it is seen."""

    def __init__(self, emit: Callable[[dict], None], inbox: Inbox | None = None):
        self.emit, self.inbox = emit, inbox
        self.tool_calls: list[dict] = []
        self.by_use_id: dict[str, dict] = {}
        self.result: dict | None = None
        self.results: list[dict] = []
        self.call_context: dict[str, int] = {}  # API response id -> context size of that one call
        self.structured_calls: list[dict] = []  # every StructuredOutput call's input, in order
        self.text_lines: list[str] = []          # output lines that are not stream-json (plain-text errors)

    def feed(self, line: str) -> None:
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            if line.strip():
                self.text_lines = (self.text_lines + [line.rstrip()])[-40:]
            return
        if not isinstance(msg, dict):
            return
        if msg.get("type") == "assistant":
            m = msg["message"]
            u = m.get("usage") or {}
            call_id = m.get("id") or f"_{len(self.call_context)}"
            ctx = sum(u.get(k, 0) or 0 for k in ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"))
            if ctx:  # one API response can arrive as several assistant messages; key by its id
                if call_id not in self.call_context:
                    self.emit({"type": "call", "call_id": call_id, "context": ctx})   # once per API call
                self.call_context[call_id] = ctx
            if u:   # later messages of the same call carry updated output counts: send each
                self.emit({"type": "usage", "call_id": call_id, "model": m.get("model", ""), "usage": u})
            for block in m.get("content", []):
                if block.get("type") != "tool_use":
                    continue
                if block["name"] == "StructuredOutput":
                    self.structured_calls.append(block.get("input", {}))
                    continue
                call = {"tool": block["name"], "input": block.get("input", {})}
                self.tool_calls.append(call)
                self.by_use_id[block.get("id")] = call
                if self.inbox:
                    self.inbox.calls = len(self.tool_calls)
                self.emit({"type": "tool_use", "id": block.get("id"), "tool": call["tool"], "input": call["input"]})
        elif msg.get("type") == "user":
            if msg.get("isReplay") and self.inbox:   # a message we wrote, echoed as the CLI takes it in
                uid = msg.get("uuid", "")
                if uid in self.inbox.sent and uid not in self.inbox.echoed:
                    self.emit({"type": "steer_echo", "uid": uid, "after_calls": self.inbox.calls})
                self.inbox.echo(uid)
            # Tool results come back as user messages; pair each with its call.
            for block in (msg.get("message") or {}).get("content", []) or []:
                if isinstance(block, dict) and block.get("type") == "tool_result" and block.get("tool_use_id") in self.by_use_id:
                    call = self.by_use_id[block["tool_use_id"]]
                    call.update(summarise_result(block))
                    self.emit({"type": "tool_result", "id": block["tool_use_id"], "tool": call["tool"],
                               **{k: call[k] for k in ("result_chars", "result_error", "result_empty", "result_preview")}})
        elif msg.get("type") == "rate_limit_event":   # plan usage, as the CLI sees it (admission.py paces on it)
            info = msg.get("rate_limit_info") or {}
            self.emit({"type": "rate_limit", "status": info.get("status", ""), "window": info.get("rateLimitType", ""),
                       "resets_at": info.get("resetsAt") or 0,
                       "windows": {k: {"utilization": w.get("utilization") or 0.0, "resets_at": w.get("resetsAt") or 0}
                                   for k, w in (info.get("unifiedWindows") or {}).items() if isinstance(w, dict)}})
        elif msg.get("type") == "system" and msg.get("subtype") == "api_retry":   # the CLI retrying a failed call
            self.emit({"type": "api_retry", "attempt": msg.get("attempt"), "status": msg.get("error_status"),
                       "error": msg.get("error", ""), "delay_ms": msg.get("retry_delay_ms")})
        elif msg.get("type") == "result":
            self.results.append(msg)
            self.result = merged_result(self.results)
            self.emit({"type": "result", "is_error": bool(msg.get("is_error")), "cost_usd": msg.get("total_cost_usd")})
            if self.inbox:
                self.inbox.after_result = True
                if not self.inbox.close(only_if_idle=True) and not self.inbox.held:
                    self.inbox.close_later()   # a steer is on its way in as a further turn -- or never taken in


def drain(f, died_at: list, on_line: Callable[[str], None] | None = None) -> str:
    """Read `f` line by line until real EOF, but give up once the watched process has been dead for more than
    DEATH_GRACE_S seconds. A plain `for line in f` blocks on pipe EOF, and an escaped descendant (e.g. a sandboxed
    MCP child in its own process group) can hold the write end open forever even though `claude` itself has
    already exited -- so this watches process death (died_at, set by a background proc.wait()) instead."""
    out = []
    emit = on_line or out.append
    try:
        fd = f.fileno()
    except (AttributeError, OSError, ValueError):  # not a real pipe (e.g. a test's StringIO): EOF is guaranteed
        for line in f:
            emit(line)
        return "".join(out)
    # Read the raw fd, not the buffered text wrapper: select() can't see data already sitting in the wrapper's
    # buffer, which would delay lines and drop them if we give up on the grace timeout.
    decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
    pending = ""
    while True:
        ready, _, _ = select.select([fd], [], [], 0.5)
        if ready:
            chunk = os.read(fd, 65536)
            if not chunk:
                break  # real EOF: every writer closed
            pending += decoder.decode(chunk)
            *lines, pending = pending.split("\n")
            for line in lines:
                emit(line + "\n")
        elif died_at[0] is not None and time.monotonic() - died_at[0] > DEATH_GRACE_S:
            break  # claude exited a while ago and nothing further arrived: stop waiting on a stray descendant
    pending += decoder.decode(b"", final=True)
    if pending:
        emit(pending)
    return "".join(out)


def kill_tree(proc) -> None:
    """Kill a `claude -p` and everything it started. `claude` is often a wrapper script (e.g. pnpm's /bin/sh shim)
    around node: proc.kill() kills only the shell, and node runs the whole turn to the end regardless. The process
    runs in its own session (start_new_session), so its pid is the group id: kill the group."""
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass
    if proc.poll() is None:
        proc.kill()


def command(spec: AgentSpec, mcp_config_path: str, claude_bin: str = "claude") -> list[str]:
    """The `claude -p` argv for a spec."""
    cmd = [claude_bin, "-p", "--model", cli_model(spec.model), "--output-format", "stream-json", "--verbose",
           "--no-session-persistence", "--strict-mcp-config"]
    if spec.system:
        cmd += ["--system-prompt", spec.system]
    if spec.schema:
        cmd += ["--json-schema", json.dumps(spec.schema)]
    if spec.setting_sources is not None:
        cmd += ["--setting-sources", spec.setting_sources]
    cmd += ["--tools", ",".join(spec.tools)]
    if spec.mcp_servers:
        cmd += ["--mcp-config", mcp_config_path]
    if spec.allowed_tools:
        cmd += ["--allowedTools", *spec.allowed_tools]
    if spec.disallowed_tools:
        cmd += ["--disallowedTools", *spec.disallowed_tools]
    if spec.add_dirs:
        cmd += ["--add-dir", *spec.add_dirs]
    if spec.debug_path:
        cmd += ["--debug-file", spec.debug_path]
    if spec.steerable:
        cmd += ["--input-format", "stream-json", "--replay-user-messages"]
    return cmd


@dataclass
class AgentResult:
    """What a finished run gave: the answer (structured output when the spec had a schema, else the text), every
    tool call with its result summary, the CLI's final result message, and the measured sizes."""
    structured: Any
    text: str
    tool_calls: list[dict]
    result: dict
    usage: dict
    cost_usd: Optional[float]
    api_calls: int
    peak_context: int              # the largest context any single API call carried (what the window must hold)
    structured_calls: list[dict]   # every StructuredOutput attempt, in order (a rejected one shows up here)
    wall_ms: float


_END = object()


class AgentRun:
    """A running agent. Iterate events() for what the stream shows as it happens; wait() for the result."""

    def __init__(self, spec: AgentSpec, config: Optional[Config] = None, inbox: Optional[Inbox] = None,
                 claude_bin: Optional[str] = None):
        check_model(spec.model)
        self.spec = spec
        self.config = config or Config(provider="claude_code", model=spec.model, ledger_enabled=False)
        self.inbox = inbox if inbox is not None else (Inbox() if spec.steerable else None)
        self.claude_bin = claude_bin or os.environ.get("CLAUDE_CODE_CLI_PATH") or "claude"
        self.proc: Optional[subprocess.Popen] = None
        self.cancelled = False
        self._events: "queue.Queue" = queue.Queue()
        self._started = threading.Event()
        self._outcome: Any = None   # AgentResult or an exception
        self._thread = threading.Thread(target=self._run, name="ai-factory-agent", daemon=True)
        self._thread.start()

    # --- control -------------------------------------------------------------------------------------------
    @property
    def pid(self) -> Optional[int]:
        return self.proc.pid if self.proc else None

    def steer(self, text: str, uid: Optional[str] = None) -> tuple[str, bool]:
        """Send a message into the running turn. Returns (uid, written). Delivery is the `steer_echo` event."""
        uid = uid or str(uuid.uuid4())
        return uid, bool(self.inbox and self.inbox.send(uid, text))

    def hold(self) -> None:
        """Keep stdin open past a result (the caller is paused and may still steer)."""
        if self.inbox:
            self.inbox.held = True

    def release(self) -> None:
        if self.inbox:
            self.inbox.release()

    def cancel(self) -> None:
        """Kill the process tree now. The run ends with an AgentRunError carrying the tool calls that ran."""
        self.cancelled = True
        self._started.wait(5)
        if self.proc is not None:
            kill_tree(self.proc)

    # --- results -------------------------------------------------------------------------------------------
    def events(self) -> Iterator[dict]:
        """Every event, in order, until the run ends (the last one is `end`). One consumer."""
        while True:
            ev = self._events.get()
            if ev is _END:
                return
            yield ev

    def wait(self, timeout: Optional[float] = None) -> AgentResult:
        self._thread.join(timeout)
        if self._thread.is_alive():
            raise TimeoutError("agent run still going")
        if isinstance(self._outcome, BaseException):
            raise self._outcome
        return self._outcome

    # --- the run itself ------------------------------------------------------------------------------------
    def _emit(self, event: dict) -> None:
        if event["type"] in ("rate_limit", "api_retry", "call"):   # what admission paces on (A8)
            admission.shared().observe(event)
        self._events.put(event)

    def _run(self) -> None:
        start = time.perf_counter()
        spec = self.spec
        parser = StreamParser(self._emit, self.inbox)
        returncode, stderr = None, ""
        sink = open(spec.stream_path, "w", encoding="utf-8") if spec.stream_path else None
        try:
            if sink:
                sink.write(json.dumps({"type": "harness.request", "model": spec.model, "system_prompt": spec.system,
                                       "user_prompt": spec.prompt, "schema": spec.schema, "tags": spec.tags}) + "\n")
            with tempfile.TemporaryDirectory(prefix="ai_factory_agent_") as workdir:
                # Empty cwd: no project CLAUDE.md or settings leak into the session.
                mcp_path = Path(workdir) / "mcp.json"
                mcp_path.write_text(json.dumps({"mcpServers": spec.mcp_servers}))
                cmd = command(spec, str(mcp_path), self.claude_bin)
                # Own session/process group: a terminal Ctrl-C reaches the caller only, and cancel() kills the tree.
                self.proc = proc = subprocess.Popen(
                    cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=workdir, text=True,
                    env=model_env(spec.model, spec.local_url, spec.env), start_new_session=True)
                self._started.set()
                self._emit({"type": "started", "pid": proc.pid})
                if self.cancelled:
                    kill_tree(proc)
                killer = threading.Timer(spec.timeout_s, kill_tree, (proc,))
                killer.start()
                died_at = [None]

                def _mark_death(p=proc):
                    p.wait()
                    died_at[0] = time.monotonic()
                threading.Thread(target=_mark_death, daemon=True).start()
                try:
                    try:
                        if self.inbox is None:
                            proc.stdin.write(spec.prompt)
                            proc.stdin.close()
                        else:
                            proc.stdin.write(user_message(spec.prompt, str(uuid.uuid4())))
                            proc.stdin.flush()
                            self.inbox.attach(proc.stdin)
                    except (BrokenPipeError, OSError):
                        pass   # it died before reading: its stderr says why

                    def _feed(line):
                        parser.feed(line)
                        if sink:
                            sink.write(line)
                            sink.flush()
                    drain(proc.stdout, died_at, on_line=_feed)
                    stderr = drain(proc.stderr, died_at)
                    returncode = proc.wait()
                finally:
                    killer.cancel()
                    if self.inbox is not None:
                        self.inbox.close()   # nothing more goes in: a later steer is the caller's to carry
            self._outcome = self._conclude(parser, returncode, stderr, (time.perf_counter() - start) * 1000)
        except BaseException as exc:   # the process never ran, or something here broke: still end cleanly
            self._outcome = exc if isinstance(exc, (AgentRunError, ToolPolicyError)) else AgentRunError(
                f"agent run failed: {type(exc).__name__}: {exc}", parser.tool_calls, parser.text_lines, stderr,
                returncode, spec.debug_path)
        finally:
            self._started.set()
            wall_ms = (time.perf_counter() - start) * 1000
            if sink:
                sink.write(json.dumps({"type": "harness.exit", "returncode": returncode, "stderr": stderr[-4000:],
                                       "wall_ms": round(wall_ms)}) + "\n")
                sink.close()
            self._ledger(parser, wall_ms)
            ok = not isinstance(self._outcome, BaseException)
            self._emit({"type": "end", "ok": ok, "cancelled": self.cancelled,
                        "error": None if ok else str(self._outcome)})
            self._events.put(_END)

    def _conclude(self, parser: StreamParser, returncode, stderr: str, wall_ms: float) -> AgentResult:
        spec, result = self.spec, parser.result
        failed = result is None or result.get("is_error") or (spec.schema and not result.get("structured_output"))
        if failed or self.cancelled:
            why = "cancelled" if self.cancelled else (
                (result or {}).get("result") or (result or {}).get("subtype") or stderr[-2000:].strip()
                or " | ".join(parser.text_lines[-5:]) or "no result message")
            raise AgentRunError(f"claude -p failed (exit {returncode}): {why}", parser.tool_calls, parser.text_lines,
                                stderr[-4000:], returncode, spec.debug_path)
        answer = AgentResult(
            structured=result.get("structured_output"), text=result.get("result") or "",
            tool_calls=parser.tool_calls, result=result, usage=result.get("usage") or {},
            cost_usd=result.get("total_cost_usd"), api_calls=len(parser.call_context),
            peak_context=max(parser.call_context.values(), default=0), structured_calls=parser.structured_calls,
            wall_ms=wall_ms)
        if spec.enforce_allowed:
            allowed = set(spec.tools) | set(spec.allowed_tools) | HARNESS_TOOLS
            off = sorted({c["tool"] for c in parser.tool_calls} - allowed)
            if off:
                raise ToolPolicyError(f"the run used tools outside its allowed set: {off}", off, answer)
        return answer

    def _ledger(self, parser: StreamParser, wall_ms: float) -> None:
        """One ledger row per run (success or not), tagged, with the measured usage. Never breaks the run."""
        cfg = self.config
        if not cfg.ledger_enabled:
            return
        try:
            result = parser.result or {}
            usage = result.get("usage") or {}
            ok = not isinstance(self._outcome, BaseException)
            meta = {"usage": usage, "tags": self.spec.tags, "api_calls": len(parser.call_context),
                    "peak_context": max(parser.call_context.values(), default=0),
                    "tool_calls": len(parser.tool_calls), "kind": "agent", "cancelled": self.cancelled}
            if usage:
                meta.update(prompt_tokens=usage.get("input_tokens", 0), completion_tokens=usage.get("output_tokens", 0))
            price = None
            if cfg.pricing_enabled and result.get("total_cost_usd") is None:
                try:
                    price = resolve_price("anthropic" if self.spec.model != LOCAL_MODEL else "local", self.spec.model,
                                          pricing_path=cfg.pricing_path, max_age_days=cfg.pricing_max_age_days)
                except Exception:
                    price = None
            text = json.dumps(result.get("structured_output")) if result.get("structured_output") is not None \
                else (result.get("result") or "")
            extra = {"cost_usd": result["total_cost_usd"]} if result.get("total_cost_usd") is not None else {}
            metrics = build_metrics(input_chars=len(self.spec.prompt), output_chars=len(text),
                                    latency_ms=max(1, int(wall_ms)), success=ok, price=price,
                                    provider_metadata=meta, **extra)
            response = ProviderResponse(text=text, metadata=meta, error=None if ok else str(self._outcome))
            row_cfg = cfg if cfg.model == self.spec.model else _with(cfg, model=self.spec.model)
            write_run_to_ledger(row_cfg, self.spec.prompt, response, metrics, ok)
        except Exception as exc:   # the ledger records; it never decides
            print(f"Warning: failed to write the agent run to the ledger: {exc}", flush=True)


def _with(cfg: Config, **kw) -> Config:
    from dataclasses import replace
    return replace(cfg, **kw)


def start_agent(spec: AgentSpec, config: Optional[Config] = None, inbox: Optional[Inbox] = None,
                claude_bin: Optional[str] = None) -> AgentRun:
    """Start one agent run and return its handle at once. `config` supplies the ledger and pricing settings
    (ledger off when omitted); `inbox` lets a caller keep its own Inbox (steerable runs make one otherwise)."""
    return AgentRun(spec, config, inbox, claude_bin)


def usage_of(result: dict) -> dict:
    """Totals from a result message's usage: the whole prompt (plain + cache read + cache write), the completion,
    and the cache reads."""
    usage = result.get("usage", {})
    return {
        "prompt_tokens": sum(usage.get(k, 0) for k in ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")),
        "completion_tokens": usage.get("output_tokens", 0),
        "cache_read_tokens": usage.get("cache_read_input_tokens", 0),
    }
