"""Tests for the ai-factory MCP server tool wrappers.

These tests call the tool functions directly (FastMCP's `@mcp.tool()` registers
the function but leaves it callable), so they do not need a running MCP
transport.
"""
import json
import os
import tempfile

import pytest

pytest.importorskip("mcp", reason="mcp SDK not installed; install with `pip install -e .[mcp]`")

from ai_factory.mcp_server import server as mcp_server


@pytest.fixture
def stub_env(monkeypatch, tmp_path):
    """Point every config knob at a stub provider + temp ledger so tests are
    hermetic (no real provider call, no real file outside tmp_path)."""
    ledger = tmp_path / "LEDGER.is"
    monkeypatch.setenv("AIFACTORY_PROVIDER", "stub")
    monkeypatch.setenv("AIFACTORY_MODEL", "stub-1")
    monkeypatch.setenv("AIFACTORY_LEDGER_PATH", str(ledger))
    monkeypatch.setenv("AIFACTORY_LEDGER_FORMAT", "is")
    monkeypatch.chdir(tmp_path)  # avoid picking up the repo's aifactory.toml
    return {"ledger": ledger, "tmp": tmp_path}


def test_run_prompt_with_stub_provider(stub_env):
    result = mcp_server.run_prompt(prompt="hello")
    assert result["success"] is True
    assert result["output"] == "STUB: hello"
    assert result["metrics"]["input_chars"] == len("hello")
    assert stub_env["ledger"].exists()
    assert "(run" in stub_env["ledger"].read_text()


def test_run_prompt_with_explicit_overrides(stub_env, tmp_path):
    alt_ledger = tmp_path / "alt.is"
    result = mcp_server.run_prompt(
        prompt="world",
        provider="stub",
        model="stub-2",
        ledger_path=str(alt_ledger),
    )
    assert result["success"] is True
    assert alt_ledger.exists()
    assert "stub-2" in alt_ledger.read_text()


def test_run_prompt_failure_returns_success_false(stub_env):
    result = mcp_server.run_prompt(prompt="__FAIL__ me", max_retries=0)
    assert result["success"] is False
    assert result["output"] == ""


def test_list_models_explicit_provider(stub_env):
    result = mcp_server.list_models(provider="stub")
    assert result["provider"] == "stub"
    names = [m["name"] for m in result["models"]]
    assert "stub-1" in names
    assert "stub-2" in names


def test_list_models_uses_configured_provider(stub_env):
    result = mcp_server.list_models()
    assert result["provider"] == "stub"
    assert len(result["models"]) >= 1


def test_embed_returns_vector_by_default(stub_env):
    result = mcp_server.embed(text="hello world")
    assert result["success"] is True
    assert result["dim"] == 8
    assert "vector" in result
    assert len(result["vector"]) == 8


def test_embed_can_exclude_vector(stub_env):
    result = mcp_server.embed(text="hello world", include_vector=False)
    assert result["success"] is True
    assert result["dim"] == 8
    assert "vector" not in result


def test_append_ledger_event_is_format(stub_env, tmp_path):
    target = tmp_path / "events.is"
    out = mcp_server.append_ledger_event(
        event_type="workflow",
        data={"step": 1, "status": "started"},
        ledger_path=str(target),
        ledger_format="is",
    )
    assert out["ledger_path"] == str(target)
    content = target.read_text()
    assert "(workflow" in content
    assert "(step 1)" in content
    assert '"started"' in content


def test_append_ledger_event_json_format(stub_env, tmp_path):
    target = tmp_path / "events.jsonl"
    mcp_server.append_ledger_event(
        event_type="checkpoint",
        data={"run_id": "abc", "step": 7},
        ledger_path=str(target),
        ledger_format="json",
    )
    entry = json.loads(target.read_text().splitlines()[0])
    assert entry["event_type"] == "checkpoint"
    assert entry["run_id"] == "abc"
    assert entry["step"] == 7


def test_append_ledger_event_without_provider_configured(monkeypatch, tmp_path):
    """Ledger-only operation must work even with no provider/model configured."""
    monkeypatch.delenv("AIFACTORY_PROVIDER", raising=False)
    monkeypatch.delenv("AIFACTORY_MODEL", raising=False)
    monkeypatch.chdir(tmp_path)
    target = tmp_path / "events.is"
    mcp_server.append_ledger_event(
        event_type="noted",
        data={"msg": "hi"},
        ledger_path=str(target),
    )
    assert "(noted" in target.read_text()


def test_analyze_ledger_on_runner_output(stub_env):
    mcp_server.run_prompt(prompt="alpha")
    mcp_server.run_prompt(prompt="beta")
    mcp_server.run_prompt(prompt="__FAIL__ gamma", max_retries=0)
    summary = mcp_server.analyze_ledger()
    assert summary["total_runs"] == 3
    assert summary["successful_runs"] == 2
    assert summary["failed_runs"] == 1
    assert summary["success_rate_percent"] == pytest.approx(200 / 3)
    assert summary["most_used_model"] == "stub-1"
    assert "stub" in summary["provider_stats"]


def test_analyze_ledger_missing_file_is_empty(stub_env, tmp_path):
    summary = mcp_server.analyze_ledger(ledger_path=str(tmp_path / "nope.is"))
    assert summary["total_runs"] == 0


def test_mcp_instance_registers_all_tools():
    """Smoke check: the FastMCP instance exposes the five tools."""
    expected = {
        "run_prompt",
        "list_models",
        "embed",
        "append_ledger_event",
        "analyze_ledger",
    }
    # FastMCP stores tools in an internal manager; access via the public list.
    import asyncio
    tools = asyncio.run(mcp_server.mcp.list_tools())
    names = {t.name for t in tools}
    assert expected.issubset(names), f"missing tools: {expected - names}"
