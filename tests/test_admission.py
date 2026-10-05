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


def test_a_warning_alone_holds_nothing_the_caps_and_pacing_do():
    """The CLI warns from 75% of a window: that is not a reason to run fewer at once (axChat bnoobs 2026-10-06: the
    rate is what is limited, not how many run) -- the cap and the pacing decide."""
    a = Admission(total=4, clock=Clock())
    a.observe(limit("allowed_warning", "seven_day", 9000, seven_day=0.8))
    assert a.admit("x").ok and a.admit("y").ok


DAY = 86400


def test_a_window_has_its_own_cap():
    a = Admission(caps={"five_hour": 0.9}, clock=Clock())
    a.observe(limit("allowed", "five_hour", 5000, five_hour=0.9, seven_day=0.92))
    d = a.check("x")
    assert (d.reason, d.until) == ("usage", 5000) and "five_hour usage at 90% (cap 90%)" in d.detail
    a.observe(limit("allowed", "five_hour", 5000, five_hour=0.89, seven_day=0.92))
    assert a.check("x").ok                                   # seven_day keeps the default 95%


def test_a_paced_window_waits_while_ahead_of_its_line_until_the_line_catches_up():
    c = Clock(0.0)
    a = Admission(caps={"seven_day": 0.9}, paced=("seven_day",), pace_slack=0.1, clock=c)
    a.observe(limit("allowed", "seven_day", 7 * DAY, seven_day=0.5))   # day 0 of 7: 9% allowed
    d = a.check("x")
    assert d.reason == "pace" and "seven_day usage 50% is ahead of its pace (9% by now" in d.detail
    # on the line when 0.9 * (t/7d + 0.1) == 0.5: t = (0.5/0.9 - 0.1) * 7d
    assert abs(d.until - (0.5 / 0.9 - 0.1) * 7 * DAY) < 1
    c.t = d.until + 1
    assert a.check("x").ok
    assert a.check("x", paced=False).ok
    c.t = 0.0
    assert a.check("x", paced=False).ok                      # a person's turn: not paced
    a.observe(limit("allowed", "seven_day", 7 * DAY, seven_day=0.95))
    assert a.check("x", paced=False).reason == "usage"       # ...but the cap holds it


def test_pacing_and_caps_bind_only_the_plans_provider():
    a = Admission(caps={"five_hour": 0.9}, paced=("seven_day",), clock=Clock(0.0))
    a.observe(limit("allowed", "seven_day", 7 * DAY, five_hour=0.95, seven_day=0.8))
    assert a.check("x").reason == "usage" and a.check("x", provider="claude_code").reason == "usage"
    assert a.check("x", provider="local").ok and a.check("x", provider="anthropic").ok


def test_an_api_budget_holds_until_enough_spend_ages_out_of_its_period():
    c = Clock(0.0)
    a = Admission(budgets={"anthropic": (1.0, 3600)}, clock=c)
    for t, usd in ((0, 0.4), (600, 0.4), (1200, 0.3)):
        c.t = t
        a.observe({"type": "spend", "provider": "anthropic", "usd": usd})
    d = a.check("sonnet", provider="anthropic")
    assert (d.reason, d.until) == ("budget", 3600) and "$1.10 in the last 1 h (budget $1.00)" in d.detail
    assert a.check("sonnet").ok and a.check("x", provider="openai").ok
    c.t = 3601
    assert a.check("sonnet", provider="anthropic").ok      # $0.70 in the last hour
    assert a.state()["spent"] == {"anthropic": 0.7}


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


def test_a_paid_runs_cost_is_spend_its_providers_budget_paces_on(tmp_path):
    """runner.run feeds what a priced call cost to admission.shared(): the budget sees real spend, not a guess."""
    from ai_factory import run
    from ai_factory.config import Config
    table = tmp_path / "pricing.toml"
    table.write_text('[meta]\nfetched_at = 2999-01-01\n\n[stub."stub-1"]\ninput_per_1m = 1000000.0\n'
                     'output_per_1m = 1000000.0\n')
    shared = Admission(budgets={"stub": (0.000001, 3600)})
    admission.set_shared(shared)
    r = run("hello world", Config(provider="stub", model="stub-1", ledger_path=str(tmp_path / "L.is"),
                                  pricing_path=str(table)))
    assert r.success and r.metrics.cost_usd
    assert shared.state()["spent"]["stub"] == round(r.metrics.cost_usd, 4)
    assert shared.check("stub-1", provider="stub").reason == "budget"
