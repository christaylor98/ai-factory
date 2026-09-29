"""start_agent(): a streamed, steerable, cancellable `claude -p` agent run (axChat CONTROLLER_SPEC §6.2, A1-A2).

Runs against tests/fixtures/fake_claude.py, which replays a scripted stream-json the shape the real CLI writes
(system init, assistant messages with usage and tool_use, user tool_results, isReplay echoes, result)."""
import json
import os
import sys
import time
from pathlib import Path

import pytest

from ai_factory import Config
from ai_factory.agent import (AgentRunError, AgentSpec, ToolPolicyError, check_model, cli_model, command, model_env,
                              start_agent)

FAKE = Path(__file__).parent / "fixtures" / "fake_claude.py"
ANSWER = {"type": "object", "properties": {"answer": {"type": "integer"}}, "required": ["answer"]}


def usage(inp, out, read=0, write=0):
    return {"input_tokens": inp, "output_tokens": out, "cache_read_input_tokens": read,
            "cache_creation_input_tokens": write,
            "cache_creation": {"ephemeral_5m_input_tokens": write, "ephemeral_1h_input_tokens": 0}}


def assistant(mid, u, *blocks):
    return {"type": "assistant", "message": {"id": mid, "model": "claude-sonnet-5", "usage": u, "content": list(blocks)}}


def tool_use(tid, name, inp):
    return {"type": "tool_use", "id": tid, "name": name, "input": inp}


def tool_result(tid, text):
    return {"type": "user", "message": {"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": tid, "content": [{"type": "text", "text": text}]}]}}


def result(structured=None, text="", cost=0.0123, u=None, error=False):
    r = {"type": "result", "subtype": "error_during_execution" if error else "success", "is_error": error,
         "result": text, "total_cost_usd": cost, "usage": u or usage(10, 5, 100, 20), "num_turns": 2}
    if structured is not None:
        r["structured_output"] = structured
    return r


def good_stream(answer=42):
    return [
        {"type": "system", "subtype": "init", "tools": ["mcp__axt__read"], "model": "claude-sonnet-5"},
        assistant("msg_1", usage(10, 3, 1000, 200), tool_use("tu_1", "mcp__axt__read", {"path": "a.py"})),
        tool_result("tu_1", "def f(): pass"),
        assistant("msg_2", usage(12, 8, 1200, 0), tool_use("so_1", "StructuredOutput", {"answer": answer})),
        tool_result("so_1", "ok"),
        result({"answer": answer}),
    ]


@pytest.fixture
def fake(tmp_path):
    """fake(lines, **script) -> (spec kwargs that route to the fake, paths it writes)."""
    def make(lines, **script):
        out = {"argv": tmp_path / "argv.json", "stdin": tmp_path / "stdin.json"}
        path = tmp_path / "script.json"
        path.write_text(json.dumps({"lines": lines, "argv_out": str(out["argv"]), "stdin_out": str(out["stdin"]),
                                    **script}))
        env = {**os.environ, "FAKE_CLAUDE_SCRIPT": str(path)}
        return {"env": env}, out
    return make


def go(spec_kw, **kw):
    return start_agent(AgentSpec(**{"prompt": "do it", "allowed_tools": ["mcp__axt__read"], **spec_kw, **kw}),
                       claude_bin=f"{FAKE}")


# --- the argv and the environment ----------------------------------------------------------------------------

def test_the_command_passes_the_spec_through():
    spec = AgentSpec(prompt="p", model="haiku", system="S", schema=ANSWER, allowed_tools=["a", "b"],
                     disallowed_tools=["c"], mcp_servers={"axt": {}}, add_dirs=["/r"], setting_sources="project",
                     steerable=True, debug_path="/d")
    argv = command(spec, "/tmp/mcp.json")
    assert argv[:4] == ["claude", "-p", "--model", "haiku"]
    for flag, value in (("--system-prompt", "S"), ("--tools", ""), ("--mcp-config", "/tmp/mcp.json"),
                        ("--setting-sources", "project"), ("--add-dir", "/r"), ("--debug-file", "/d"),
                        ("--output-format", "stream-json"), ("--input-format", "stream-json")):
        assert argv[argv.index(flag) + 1] == value, flag
    assert json.loads(argv[argv.index("--json-schema") + 1]) == ANSWER
    assert argv[argv.index("--allowedTools") + 1:argv.index("--allowedTools") + 3] == ["a", "b"]
    assert "--replay-user-messages" in argv and "--strict-mcp-config" in argv


def test_no_schema_no_mcp_no_steering_means_no_flags_for_them():
    argv = command(AgentSpec(prompt="p", tools=["Read", "Grep"]), "/x")
    assert "--json-schema" not in argv and "--mcp-config" not in argv and "--input-format" not in argv
    assert argv[argv.index("--tools") + 1] == "Read,Grep"


def test_models_are_checked_and_local_points_at_the_local_server():
    assert check_model("sonnet") == "sonnet" and check_model("claude-opus-5[1m]") and check_model("local")
    with pytest.raises(ValueError):
        check_model("openai/gpt-4o-mini")
    env = model_env("local", "http://127.0.0.1:9", base={"ANTHROPIC_AUTH_TOKEN": "t", "PATH": "/bin"})
    assert env["ANTHROPIC_BASE_URL"] == "http://127.0.0.1:9" and env["ANTHROPIC_API_KEY"] == "local"
    assert "ANTHROPIC_AUTH_TOKEN" not in env and cli_model("local") == "claude-local"
    assert model_env("sonnet", base={"ANTHROPIC_API_KEY": "k"}) == {"ANTHROPIC_API_KEY": "k"}   # a user's key stays


# --- a run -----------------------------------------------------------------------------------------------------

def test_a_run_streams_events_then_gives_the_structured_answer(fake, tmp_path):
    kw, out = fake(good_stream())
    stream = tmp_path / "stream.jsonl"
    run = go(kw, schema=ANSWER, stream_path=str(stream), tags={"session": "s1"})
    events = list(run.events())
    types = [e["type"] for e in events]
    assert types == ["started", "call", "usage", "tool_use", "tool_result", "call", "usage", "result", "end"]
    assert events[1] == {"type": "call", "call_id": "msg_1", "context": 1210}
    assert events[3]["tool"] == "mcp__axt__read" and events[4]["result_preview"] == "def f(): pass"
    assert events[-1] == {"type": "end", "ok": True, "cancelled": False, "error": None}
    r = run.wait()
    assert r.structured == {"answer": 42} and r.cost_usd == 0.0123
    assert r.api_calls == 2 and r.peak_context == 1212 and r.structured_calls == [{"answer": 42}]
    assert [c["tool"] for c in r.tool_calls] == ["mcp__axt__read"]
    assert json.loads(out["stdin"].read_text()) == ["do it"]          # the prompt went in on stdin
    lines = [json.loads(x) for x in stream.read_text().splitlines()]
    assert lines[0]["type"] == "harness.request" and lines[0]["tags"] == {"session": "s1"}
    assert lines[-1]["type"] == "harness.exit" and lines[-1]["returncode"] == 0
    assert len(lines) == len(good_stream()) + 2


def test_without_a_schema_the_answer_is_the_text(fake):
    kw, _ = fake([result(text="done: 3 files")])
    r = go(kw).wait()
    assert r.structured is None and r.text == "done: 3 files"


def test_a_failed_run_keeps_the_tool_calls_that_ran(fake):
    kw, _ = fake(good_stream()[:3], exit=1, stderr="API Error: 529 overloaded\n")
    run = go(kw, schema=ANSWER)
    with pytest.raises(AgentRunError) as err:
        run.wait()
    assert err.value.returncode == 1 and "529" in str(err.value) and "overloaded" in err.value.stderr
    assert [c["tool"] for c in err.value.tool_calls] == ["mcp__axt__read"]   # its side effects are real


def test_a_schema_with_no_structured_answer_is_a_failure(fake):
    kw, _ = fake([result(text="I refuse")])
    with pytest.raises(AgentRunError):
        go(kw, schema=ANSWER).wait()


def test_a_tool_outside_the_allowed_set_fails_the_run(fake):
    lines = [assistant("m", usage(1, 1), tool_use("t", "Bash", {"command": "rm -rf /"})), tool_result("t", ""),
             result(text="ok")]
    kw, _ = fake(lines)
    with pytest.raises(ToolPolicyError) as err:
        go(kw).wait()
    assert err.value.tools == ["Bash"] and err.value.result.text == "ok"
    kw, _ = fake(lines)
    assert go(kw, enforce_allowed=False).wait().text == "ok"


def test_a_call_to_a_tool_that_does_not_exist_never_ran_and_does_not_fail_the_run(fake):
    refused = {"type": "user", "message": {"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": "t", "is_error": True,
         "content": "<tool_use_error>Error: No such tool available: run</tool_use_error>"}]}}
    lines = [assistant("m", usage(1, 1), tool_use("t", "run", {"command": "pytest"})), refused, result(text="ok")]
    kw, _ = fake(lines)
    assert go(kw).wait().text == "ok"
    ran = [assistant("m", usage(1, 1), tool_use("t", "run", {"command": "pytest"})), tool_result("t", "ok"),
           result(text="ok")]
    kw, _ = fake(ran)
    with pytest.raises(ToolPolicyError):          # one that answered (it exists and ran) still fails the run
        go(kw).wait()
    failed = {"type": "user", "message": {"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": "t", "is_error": True, "content": "Error: exit 1"}]}}
    kw, _ = fake([assistant("m", usage(1, 1), tool_use("t", "run", {"command": "pytest"})), failed, result(text="ok")])
    with pytest.raises(ToolPolicyError):          # it ran and failed: it existed, so it still fails the run
        go(kw).wait()


def test_cancel_kills_the_process_tree_at_once(fake):
    kw, _ = fake(good_stream(), sleep_between=30)
    run = go(kw, schema=ANSWER)
    events = run.events()
    assert next(events)["type"] == "started"
    pid, t0 = run.pid, time.monotonic()
    run.cancel()
    with pytest.raises(AgentRunError) as err:
        run.wait(timeout=10)
    assert time.monotonic() - t0 < 8 and "cancelled" in str(err.value)
    assert [e for e in events][-1]["cancelled"] is True
    with pytest.raises(ProcessLookupError):
        os.kill(pid, 0)


def test_a_run_past_its_timeout_is_killed(fake):
    kw, _ = fake(good_stream(), sleep_before=30)
    t0 = time.monotonic()
    with pytest.raises(AgentRunError):
        go(kw, schema=ANSWER, timeout_s=1).wait(timeout=15)
    assert time.monotonic() - t0 < 10


def test_a_steer_goes_in_and_its_delivery_is_the_echo(fake):
    lines = good_stream()
    lines.insert(3, {"$wait_for_steer": True})     # the CLI takes it in at the next tool boundary
    kw, out = fake(lines)
    run = go(kw, schema=ANSWER, steerable=True)
    events = run.events()
    while next(events)["type"] != "tool_result":
        pass
    uid, written = run.steer("also check b.py")
    assert written
    rest = list(events)
    echo = [e for e in rest if e["type"] == "steer_echo"]
    assert echo == [{"type": "steer_echo", "uid": uid, "after_calls": 1}]    # 1 tool call ran before it
    assert run.wait().structured == {"answer": 42}
    got = [json.loads(x) for x in json.loads(out["stdin"].read_text())]
    assert got[0]["message"]["content"][0]["text"] == "do it"
    assert got[1]["uuid"] == uid and got[1]["message"]["content"][0]["text"] == "also check b.py"


def test_a_late_steer_run_as_a_further_turn_sums_the_usage(fake):
    lines = good_stream()[:-1] + [result({"answer": 1}, cost=0.01, u=usage(10, 5)),
                                  result({"answer": 2}, cost=0.03, u=usage(7, 4))]
    kw, _ = fake(lines)
    r = go(kw, schema=ANSWER).wait()
    assert r.structured == {"answer": 2} and r.cost_usd == 0.03
    assert r.usage["input_tokens"] == 17 and r.usage["output_tokens"] == 9


# --- the ledger (A2) -------------------------------------------------------------------------------------------

def _ledger_cfg(tmp_path):
    return Config(provider="claude_code", model="sonnet", ledger_path=str(tmp_path / "ledger.jsonl"),
                  ledger_format="json", pricing_enabled=False)


def test_each_run_writes_one_tagged_ledger_row(fake, tmp_path):
    cfg = _ledger_cfg(tmp_path)
    kw, _ = fake(good_stream())
    start_agent(AgentSpec(prompt="do it", allowed_tools=["mcp__axt__read"], schema=ANSWER, tags={"request": "R7"},
                          **kw), config=cfg, claude_bin=str(FAKE)).wait()
    kw, _ = fake([], exit=1, stderr="boom")
    with pytest.raises(AgentRunError):
        start_agent(AgentSpec(prompt="again", tags={"request": "R8"}, **kw), config=cfg, claude_bin=str(FAKE)).wait()
    rows = [json.loads(x) for x in (tmp_path / "ledger.jsonl").read_text().splitlines()]
    assert [r["success"] for r in rows] == [True, False]
    meta = rows[0]["metrics"]["provider_metadata"]
    assert meta["tags"] == {"request": "R7"} and meta["kind"] == "agent" and meta["api_calls"] == 2
    assert rows[0]["metrics"]["cost_usd"] == 0.0123
    assert rows[1]["metrics"]["provider_metadata"]["tags"] == {"request": "R8"}


def test_no_config_means_no_ledger(fake, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    kw, _ = fake(good_stream())
    go(kw, schema=ANSWER).wait()
    assert not any(tmp_path.glob("LEDGER*"))


# --- the inbox at a result (lifted from axChat's K84/K86/K95 tests) ---------------------------------------------

class _Stdin:
    def __init__(self):
        self.lines, self.closed = [], False

    def write(self, text):
        self.lines.append(text)

    def flush(self):
        pass

    def close(self):
        self.closed = True


def _parser_with_inbox():
    from ai_factory.agent import Inbox, StreamParser
    events, box, stdin = [], Inbox(), _Stdin()
    box.attach(stdin)
    return StreamParser(events.append, box), box, stdin, events


def test_only_our_own_message_counts_as_a_delivered_steer():            # K84
    p, box, stdin, events = _parser_with_inbox()
    box.send("mine", "steer")
    p.feed(json.dumps({"type": "user", "isReplay": True, "uuid": "the-prompt", "message": {"content": []}}))
    assert box.echoed == {} and not [e for e in events if e["type"] == "steer_echo"]
    p.feed(json.dumps({"type": "user", "isReplay": True, "uuid": "mine", "message": {"content": []}}))
    assert list(box.echoed) == ["mine"]


def test_stdin_stays_open_at_a_result_while_a_steer_is_on_its_way(monkeypatch):   # K86
    import ai_factory.agent as agent_mod
    monkeypatch.setattr(agent_mod, "STEER_WAIT_S", 30)
    p, box, stdin, _ = _parser_with_inbox()
    box.send("late", "x")
    p.feed(json.dumps(result({"a": 1})))
    assert not stdin.closed
    p.feed(json.dumps({"type": "user", "isReplay": True, "uuid": "late", "message": {"content": []}}))
    p.feed(json.dumps(result({"a": 2})))
    assert stdin.closed


def test_a_paused_run_keeps_stdin_open_at_a_result(monkeypatch):          # K95
    import ai_factory.agent as agent_mod
    monkeypatch.setattr(agent_mod, "STEER_WAIT_S", 30)
    p, box, stdin, _ = _parser_with_inbox()
    box.held = True
    p.feed(json.dumps(result({"a": 1})))
    assert not stdin.closed
    box.release()
    assert stdin.closed


def test_an_idle_run_closes_stdin_at_its_result():
    p, box, stdin, _ = _parser_with_inbox()
    p.feed(json.dumps(result({"a": 1})))
    assert stdin.closed
