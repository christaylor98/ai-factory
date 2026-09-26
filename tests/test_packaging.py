"""A5/A6 (axChat CONTROLLER_SPEC §6.2): importing ai_factory has no side effects on the environment, and the core
works with no provider SDK installed."""
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import tomllib

ROOT = Path(__file__).resolve().parents[1]


def _py(code: str, cwd: Path, env: dict | None = None) -> subprocess.CompletedProcess:
    e = {k: v for k, v in os.environ.items() if not k.endswith("_API_KEY")}
    e.update(PYTHONPATH=str(ROOT / "src"), **(env or {}))
    return subprocess.run([sys.executable, "-c", textwrap.dedent(code)], cwd=cwd, env=e,
                          capture_output=True, text=True, timeout=60)


def test_importing_ai_factory_leaves_the_environment_alone(tmp_path):
    (tmp_path / ".env").write_text("ANTHROPIC_API_KEY=sk-from-dotenv\nAIF_TEST_MARKER=1\n")
    r = _py("""
        import os, ai_factory
        print(os.environ.get("ANTHROPIC_API_KEY"), os.environ.get("AIF_TEST_MARKER"))
    """, tmp_path)
    assert r.returncode == 0, r.stderr
    assert r.stdout.split() == ["None", "None"]


def test_load_env_is_how_a_caller_opts_in_and_it_never_overrides(tmp_path):
    (tmp_path / ".env").write_text("AIF_TEST_MARKER=from-file\nAIF_TEST_KEEP=from-file\n")
    r = _py("""
        import os, ai_factory
        print(ai_factory.load_env(), os.environ["AIF_TEST_MARKER"], os.environ["AIF_TEST_KEEP"])
    """, tmp_path, {"AIF_TEST_KEEP": "already-set"})
    assert r.returncode == 0, r.stderr
    assert r.stdout.split() == ["True", "from-file", "already-set"]


def test_the_core_runs_with_every_provider_sdk_missing(tmp_path):
    r = _py("""
        import sys
        class Block:   # as if google-genai, openai and anthropic were not installed
            def find_spec(self, name, path=None, target=None):
                if name.split(".")[0] in ("openai", "anthropic", "google"):
                    raise ImportError(f"blocked: {name}")
        sys.meta_path.insert(0, Block())
        import ai_factory
        from ai_factory.provider_registry import list_provider_names
        assert {"stub", "claude_code", "ollama"} <= set(list_provider_names())
        r = ai_factory.run("hi", ai_factory.Config(provider="stub", model="m", ledger_enabled=False))
        missing = ai_factory.run("hi", ai_factory.Config(provider="openai", model="m", ledger_enabled=False))
        assert not missing.success and "install" in missing.error.lower(), missing.error
        print(r.success)
    """, tmp_path)
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "True"


def test_provider_sdks_are_extras_not_core_dependencies():
    meta = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
    core = " ".join(meta["dependencies"])
    for sdk in ("google-genai", "openai", "anthropic"):
        assert sdk not in core
    extras = meta["optional-dependencies"]
    assert {"gemini", "openai", "anthropic", "local", "all"} <= set(extras)
