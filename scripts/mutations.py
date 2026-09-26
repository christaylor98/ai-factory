#!/usr/bin/env python3
"""Mutation check: would the tests notice if the code broke in these specific ways?

Each mutation replaces one piece of source with a broken version in a temporary copy of the repo, runs the test
file that should catch it, and expects it to FAIL. A mutation the tests survive is a gap in the tests. Add one for
every fix and feature (a rule carried over from axChat's scripts/disconformance.py).

    python scripts/mutations.py            # all
    python scripts/mutations.py -k steer   # only those whose name contains "steer"
"""
import argparse
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AGENT = "src/ai_factory/agent.py"
T_AGENT = "tests/test_agent.py"


@dataclass
class Mutation:
    name: str
    file: str
    old: str
    new: str
    tests: str


MUTATIONS = [
    # agent runs (lifted from axChat 2026-09-27; the K-numbers are axChat's TUI_REQUIREMENTS)
    Mutation("steer: delivery never reported", AGENT,
             'self.emit({"type": "steer_echo", "uid": uid, "after_calls": self.inbox.calls})', "pass", T_AGENT),
    Mutation("K84: an echo of any message counts as our steer delivered", AGENT,
             "        if uid in self.sent and uid not in self.echoed:", "        if uid not in self.echoed:", T_AGENT),
    Mutation("K83: the prompt goes in as plain text on a steerable run", AGENT,
             "proc.stdin.write(user_message(spec.prompt, str(uuid.uuid4())))", "proc.stdin.write(spec.prompt)", T_AGENT),
    Mutation("K86: stdin closed at a result while a steer is on its way", AGENT,
             "            if only_if_idle and (self.outstanding() or self.held):",
             "            if only_if_idle and self.held:", T_AGENT),
    Mutation("K95: a run that ends its turn while paused closes stdin", AGENT,
             "            if only_if_idle and (self.outstanding() or self.held):",
             "            if only_if_idle and self.outstanding():", T_AGENT),
    Mutation("K86: usage of several results not summed", AGENT, "usage[k] = usage.get(k, 0) + v", "usage[k] = v", T_AGENT),
    Mutation("cost: usage never reported as it streams", AGENT,
             '                self.emit({"type": "usage", "call_id": call_id', '                pass  # ({"type": "usage", "call_id": call_id',
             T_AGENT),
    Mutation("local: claude -p not pointed at the local server", AGENT,
             "env.update(ANTHROPIC_BASE_URL=local_url,", "env.update(ANTHROPIC_BASE_URL=DEFAULT_LOCAL_URL,", T_AGENT),
    Mutation("cancel: the process is not killed", AGENT,
             "        if self.proc is not None:\n            kill_tree(self.proc)", "        pass", T_AGENT),
    Mutation("policy: a tool outside the allowed set passes", AGENT,
             "            if off:\n                raise ToolPolicyError", "            if False:\n                raise ToolPolicyError",
             T_AGENT),
    Mutation("schema: a run with no structured answer passes", AGENT,
             '(spec.schema and not result.get("structured_output"))', "False", T_AGENT),
    Mutation("ledger: a failed run writes no row", AGENT,
             "        if not cfg.ledger_enabled:\n            return",
             "        if not cfg.ledger_enabled or isinstance(self._outcome, BaseException):\n            return", T_AGENT),
    # packaging and single prompts
    Mutation("A5: importing ai_factory loads .env again", "src/ai_factory/__init__.py",
             "from .env import load_env\n", "from .env import load_env\nload_env()\n", "tests/test_packaging.py"),
    Mutation("A4: a provider silently drops a system prompt it can't take", "src/ai_factory/runner.py",
             "        if unsupported:   # refused, not silently dropped", "        if False:", "tests/test_system_and_schema.py"),
    Mutation("A3: 1-hour cache writes priced as 5-minute ones", "src/ai_factory/metrics.py",
             "rate(getattr(price, \"cache_write_1h_per_1m\", None), _CACHE_WRITE_1H_MULTIPLIER, w1h)",
             "rate(price.cache_write_per_1m, _CACHE_WRITE_MULTIPLIER, w1h)", "tests/test_usage_cost.py"),
]


def run_tests(work: Path, tests: str, timeout: float = 90) -> bool:
    """True when the tests pass. A run past `timeout` is a failure (a hang is caught too): its whole process group is
    killed, since a fake `claude` it started would otherwise hold the output pipe open."""
    import os
    import signal
    p = subprocess.Popen([sys.executable, "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider", "-o", "addopts=",
                          *tests.split()], cwd=work, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=True)
    try:
        return p.wait(timeout=timeout) == 0
    except subprocess.TimeoutExpired:
        os.killpg(p.pid, signal.SIGKILL)
        p.wait()
        return False


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("-k", default="", help="only mutations whose name contains this")
    args = ap.parse_args()
    chosen = [m for m in MUTATIONS if args.k in m.name]
    with tempfile.TemporaryDirectory(prefix="aif-mutations-") as tmp:
        work = Path(tmp) / "repo"
        shutil.copytree(ROOT, work, ignore=shutil.ignore_patterns(".git", ".venv", "__pycache__", "*.egg-info", "dist"))
        if not run_tests(work, " ".join(sorted({m.tests for m in chosen}))):
            print("baseline must pass first")
            return 2
        survived = []
        for m in chosen:
            path = work / m.file
            original = path.read_text()
            if original.count(m.old) != 1:
                print(f"STALE     {m.name}: found the target text {original.count(m.old)} times")
                survived.append(m.name)
                continue
            path.write_text(original.replace(m.old, m.new))
            try:
                passed = run_tests(work, m.tests)
            finally:
                path.write_text(original)
            print(("SURVIVED" if passed else "caught  ") + f"  {m.name}", flush=True)
            if passed:
                survived.append(m.name)
    print(f"\n{len(chosen) - len(survived)}/{len(chosen)} mutations caught")
    return 1 if survived else 0


if __name__ == "__main__":
    sys.exit(main())
