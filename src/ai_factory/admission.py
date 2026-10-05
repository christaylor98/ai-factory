"""
Admission and pacing: whether one more agent run may start now.

A scheduler asks `admit(key)` before it starts a run and calls `release(key)` when the run ends. The answer comes
from three things, all measured, none guessed:

- concurrency: at most `total` runs at once, and at most `per_key[key]` of one kind (a model, or a local GPU that
  serves one request at a time);
- back-off: after the provider says it is rate limited or overloaded (HTTP 429 / 529), no new run starts for a
  while -- `backoff_base_s`, doubling with each further one, up to `backoff_max_s`; a response that gets through
  ends the streak;
- plan usage (the claude CLI's provider, "claude_code"): the CLI reports how much of each usage window (five hours,
  seven days) is used -- the whole account's, a person's own prompting too. No new run starts while a window is at
  its cap (`caps[window]`, else `usage_cap`) or was refused outright, until that window resets. A window in `paced`
  is spread over its length: the share it may have used by now rises in a straight line from `pace_slack` of its cap
  at the start to the whole cap at the reset, and while it is ahead of that line a new run waits until the line
  catches up (`admit(key, paced=False)` skips the pacing -- a person's turn -- never the caps);
- money (an API provider, paid per call): `budgets[provider] = (usd, period_s)` -- no new run of that provider starts
  while what it spent in the last period_s (`observe({"type": "spend", ...})`, fed by runner.run) is the budget or
  more, until enough of it is older than the period.

It never stops a run that has started: it only decides when the next one starts. The ledger stays observational;
this is the part that acts.

    adm = shared()                       # the process's one gate (agent runs feed it their stream events)
    d = adm.admit("sonnet")
    if d.ok: ...run..., then adm.release("sonnet")
    else:    try again at d.until (0: when a running one ends)
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

RETRY_STATUSES = (429, 529)   # rate limited, overloaded
WINDOW_S = {"five_hour": 5 * 3600, "seven_day": 7 * 86400}   # a window's length, for pacing it
PLAN = ("", "claude_code")    # the providers the plan windows bind (the CLI's)


@dataclass(frozen=True)
class Decision:
    ok: bool
    reason: str = ""      # why not: "concurrency", "per_key", "backoff", "usage", "refused", "pace", "budget"
    until: float = 0.0    # when asking again can change the answer (0: when a running one is released)
    detail: str = ""      # one line for a person


@dataclass
class Window:
    utilization: float = 0.0
    resets_at: float = 0.0
    status: str = "allowed"   # allowed | allowed_warning | rejected (the CLI's words)


@dataclass
class Admission:
    total: Optional[int] = None                    # None: no overall limit
    per_key: dict = field(default_factory=dict)    # {key: max at once}
    usage_cap: float = 0.95                        # a window this full holds new runs until it resets
    caps: dict = field(default_factory=dict)       # {window: cap} -- overrides usage_cap per window
    paced: tuple = ()                              # windows spread over their length (e.g. ("seven_day",))
    pace_slack: float = 0.1                        # the share of the cap a paced window may use at once
    budgets: dict = field(default_factory=dict)    # {provider: (usd, period_s)}
    backoff_base_s: float = 30.0
    backoff_max_s: float = 900.0
    clock: Callable[[], float] = time.time

    def __post_init__(self):
        self.running: dict[str, int] = {}
        self.windows: dict[str, Window] = {}
        self.backoff_until = 0.0
        self.streak = 0
        self.spent: dict[str, list[tuple[float, float]]] = {}   # provider -> [(when, usd)]
        self._lock = threading.Lock()

    # --- asking ------------------------------------------------------------------------------------------------
    def check(self, key: str, paced: bool = True, provider: str = "") -> Decision:
        """What admit(key) would answer, without taking a slot."""
        now = self.clock()
        with self._lock:
            return self._decide(key, now, paced, provider)

    def admit(self, key: str, paced: bool = True, provider: str = "") -> Decision:
        """May a run of `key` (on `provider`; "" = the CLI's plan) start now? When it may, it counts as running until
        release(key). paced=False: the plan windows' pacing doesn't hold it (their caps still do)."""
        now = self.clock()
        with self._lock:
            d = self._decide(key, now, paced, provider)
            if d.ok:
                self.running[key] = self.running.get(key, 0) + 1
            return d

    def release(self, key: str) -> None:
        with self._lock:
            n = self.running.get(key, 0) - 1
            if n > 0:
                self.running[key] = n
            else:
                self.running.pop(key, None)

    def cap(self, window: str) -> float:
        return float(self.caps.get(window, self.usage_cap))

    def pace(self, window: str, now: float) -> tuple[float, float]:
        """(the share of `window` it may have used by now, when its usage now would be on the line); (cap, 0) when it
        isn't paced or its length or reset is unknown."""
        w, length, cap = self.windows.get(window), WINDOW_S.get(window), self.cap(window)
        if window not in self.paced or w is None or not length or not w.resets_at or w.resets_at <= now:
            return cap, 0.0
        start = w.resets_at - length
        allowed = cap * min(1.0, (now - start) / length + self.pace_slack)
        need = (w.utilization / cap - self.pace_slack) * length if cap > 0 else length
        return allowed, start + need

    def _decide(self, key: str, now: float, paced: bool = True, provider: str = "") -> Decision:
        if provider in PLAN:
            for name, w in self.windows.items():
                if w.resets_at and w.resets_at <= now:
                    continue   # that window has reset: what we knew of it no longer holds
                if w.status == "rejected":
                    return Decision(False, "refused", w.resets_at, f"the {name} usage limit is reached")
                if w.utilization >= self.cap(name):
                    return Decision(False, "usage", w.resets_at,
                                    f"{name} usage at {w.utilization:.0%} (cap {self.cap(name):.0%})")
                allowed, until = self.pace(name, now)
                if paced and w.utilization > allowed:
                    return Decision(False, "pace", until,
                                    f"{name} usage {w.utilization:.0%} is ahead of its pace ({allowed:.0%} by now, "
                                    f"cap {self.cap(name):.0%} at the reset)")
        if provider in self.budgets:
            usd, period = self.budgets[provider]
            spent = [(t, x) for t, x in self.spent.get(provider, []) if t > now - period]
            total = sum(x for _, x in spent)
            if total >= usd:
                drop, until = total - usd, now
                for t, x in spent:      # oldest first: when enough has aged out to be under the budget
                    until = t + period
                    drop -= x
                    if drop < 0:
                        break
                return Decision(False, "budget", until, f"{provider} spent ${total:.2f} in the last "
                                f"{period / 3600:g} h (budget ${usd:.2f})")
        if self.backoff_until > now:
            return Decision(False, "backoff", self.backoff_until, "the provider said slow down (429/529)")
        n = sum(self.running.values())
        if self.total is not None and n >= self.total:
            return Decision(False, "concurrency", 0.0, f"{n} running (limit {self.total})")
        limit = self.per_key.get(key)
        if limit is not None and self.running.get(key, 0) >= limit:
            return Decision(False, "per_key", 0.0, f"{key}: {self.running.get(key, 0)} running (limit {limit})")
        return Decision(True)

    # --- what the runs report ----------------------------------------------------------------------------------
    def observe(self, event: dict) -> None:
        """An agent run's stream event: `rate_limit` (plan usage), `api_retry` (429/529 back-off), `call` (a
        response got through) or `spend` ({provider, usd}: what a paid call cost). Anything else is ignored."""
        t = event.get("type")
        now = self.clock()
        with self._lock:
            if t == "rate_limit":
                # the status is the binding window's (the CLI names it); the others report only how full they are
                for name, w in (event.get("windows") or {}).items():
                    self.windows[name] = Window(float(w.get("utilization") or 0.0), float(w.get("resets_at") or 0.0))
                name = event.get("window")
                if name:
                    cur = self.windows.setdefault(name, Window())
                    cur.status = event.get("status") or "allowed"
                    if event.get("resets_at"):
                        cur.resets_at = float(event["resets_at"])
            elif t == "api_retry" and event.get("status") in RETRY_STATUSES:
                self.streak += 1
                wait = min(self.backoff_base_s * 2 ** (self.streak - 1), self.backoff_max_s)
                self.backoff_until = max(self.backoff_until, now + wait)
            elif t == "call":
                self.streak = 0
            elif t == "spend" and event.get("usd"):
                keep = max((p for _, p in self.budgets.values()), default=0.0)
                rows = [r for r in self.spent.get(event.get("provider", ""), []) if r[0] > now - keep]
                self.spent[event.get("provider", "")] = rows + [(now, float(event["usd"]))]

    def state(self) -> dict:
        """For a status line: what is running, the windows and any back-off."""
        with self._lock:
            now = self.clock()
            return {"running": dict(self.running), "backoff_until": self.backoff_until,
                    "windows": {k: {**vars(w), "cap": self.cap(k),
                                    **({"pace": self.pace(k, now)[0]} if k in self.paced else {})}
                                for k, w in self.windows.items()},
                    "spent": {p: round(sum(x for t, x in rows if t > now - self.budgets.get(p, (0, 0))[1]), 4)
                              for p, rows in self.spent.items() if p in self.budgets}}


_SHARED: Optional[Admission] = None
_SHARED_LOCK = threading.Lock()


def shared() -> Admission:
    """The process's one gate. Agent runs feed it what their streams report (agent.AgentRun)."""
    global _SHARED
    with _SHARED_LOCK:
        if _SHARED is None:
            _SHARED = Admission()
        return _SHARED


def set_shared(adm: Optional[Admission]) -> None:
    """Replace the process's gate (a scheduler configuring its limits; a test starting clean)."""
    global _SHARED
    with _SHARED_LOCK:
        _SHARED = adm
