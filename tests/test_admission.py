"""Admission and pacing (axChat CONTROLLER_SPEC A8): whether one more agent run may start now -- concurrency, back-off
after a 429/529, plan usage. Pure, with a fake clock; the last test runs the fake CLI to show a run's stream feeds it."""
import json

import pytest

from ai_factory import admission
from ai_factory.admission import Admission

from .test_agent import FAKE, good_stream, fake   # noqa: F401  (fake is a fixture)


class Clock:
    def __init__(self, t=1000.0):
        self.t = t

    def __call__(self):
        return self.t


@pytest.fixture(autouse=True)
def clean_shared():
    admission.set_shared(None)
    yield
    admission.set_shared(None)


def limit(status="allowed", window="five_hour", resets_at=5000, **windows):
    return {"type": "rate_limit", "status": status, "window": window, "resets_at": resets_at,
            "windows": {k: {"utilization": u, "resets_at": resets_at} for k, u in windows.items()}}


def test_concurrency_overall_and_per_key_and_release_frees_a_slot():
    a = Admission(total=2, per_key={"local": 1})
    assert a.admit("local").ok
    d = a.admit("local")
    assert not d.ok and d.reason == "per_key" and d.until == 0
    assert a.admit("sonnet").ok
    assert a.admit("opus").reason == "concurrency"
    a.release("local")
    assert a.admit("opus").ok
    assert a.state()["running"] == {"sonnet": 1, "opus": 1}


def test_check_does_not_take_a_slot():
    a = Admission(total=1)
    assert a.check("x").ok and a.check("x").ok
    assert a.admit("x").ok and not a.check("x").ok


def test_a_429_backs_off_doubling_up_to_the_max_and_a_response_ends_the_streak():
    c = Clock()
    a = Admission(backoff_base_s=10, backoff_max_s=25, clock=c)
    a.observe({"type": "api_retry", "status": 429})
    d = a.admit("x")
    assert (d.ok, d.reason, d.until) == (False, "backoff", 1010)
    a.observe({"type": "api_retry", "status": 529})
    assert a.admit("x").until == 1020                      # 10, then 20
    a.observe({"type": "api_retry", "status": 429})
    assert a.admit("x").until == 1025                      # 40, capped at 25
    c.t = 1026
    assert a.admit("x").ok
    a.observe({"type": "call"})                            # one got through: the next 429 starts from the base again
    a.observe({"type": "api_retry", "status": 429})
    assert a.check("x").until == 1036


def test_a_retry_that_is_not_a_rate_limit_does_not_back_off():
    a = Admission(clock=Clock())
    a.observe({"type": "api_retry", "status": None, "error": "unknown"})
    a.observe({"type": "api_retry", "status": 500})
    assert a.admit("x").ok


def test_plan_usage_at_the_cap_holds_new_runs_until_the_window_resets():
    c = Clock()
    a = Admission(usage_cap=0.9, clock=c)
    a.observe(limit(five_hour=0.5, seven_day=0.89))
    assert a.admit("x").ok
    a.release("x")
    a.observe(limit(five_hour=0.5, seven_day=0.9))
    d = a.admit("x")
    assert (d.ok, d.reason, d.until) == (False, "usage", 5000) and "seven_day" in d.detail
    c.t = 5000                                             # the window reset: what we knew no longer holds
    assert a.admit("x").ok


def test_a_refused_window_holds_everything_until_it_resets():
    c = Clock()
    a = Admission(clock=c)
    a.observe(limit("rejected", "five_hour", 3000, five_hour=0.2))   # refused even below the cap
    d = a.admit("x")
    assert (d.ok, d.reason, d.until) == (False, "refused", 3000)
    c.t = 3001
    assert a.admit("x").ok


def test_a_warning_means_one_run_at_a_time():
    a = Admission(total=4, clock=Clock())
    a.observe(limit("allowed_warning", "seven_day", 9000, seven_day=0.8))
    assert a.admit("x").ok
    assert a.admit("y").reason == "warning"
    a.observe(limit("allowed", "five_hour", 9000, five_hour=0.1, seven_day=0.8))   # the CLI stopped warning
    assert a.admit("y").ok


def test_a_runs_stream_feeds_the_shared_gate(fake):
    """A rate_limit_event and a 429 retry in the CLI's stream reach admission.shared(), and show up as events."""
    from ai_factory.agent import AgentSpec, start_agent
    shared = Admission(clock=Clock(0))
    admission.set_shared(shared)
    rl = {"type": "rate_limit_event", "rate_limit_info": {
        "status": "allowed_warning", "resetsAt": 100, "rateLimitType": "seven_day",
        "unifiedWindows": {"five_hour": {"utilization": 0.3, "resetsAt": 50}, "seven_day": {"utilization": 0.97, "resetsAt": 100}}}}
    retry = {"type": "system", "subtype": "api_retry", "attempt": 1, "max_retries": 10, "retry_delay_ms": 500,
             "error_status": 429, "error": "rate_limit"}
    lines = good_stream()
    kw, _ = fake([lines[0], retry, rl, *lines[1:]])
    run = start_agent(AgentSpec(prompt="p", allowed_tools=["mcp__axt__read"], **kw), claude_bin=str(FAKE))
    events = [e for e in run.events()]
    run.wait()
    rate = next(e for e in events if e["type"] == "rate_limit")
    assert rate["window"] == "seven_day" and rate["windows"]["seven_day"] == {"utilization": 0.97, "resets_at": 100}
    assert next(e for e in events if e["type"] == "api_retry")["status"] == 429
    st = shared.state()
    assert st["windows"]["seven_day"]["status"] == "allowed_warning" and st["windows"]["five_hour"]["utilization"] == 0.3
    assert st["backoff_until"] > 0 and shared.streak == 0   # backed off, then the next response ended the streak
    assert shared.check("x").reason == "usage"              # 0.97 is over the default cap
