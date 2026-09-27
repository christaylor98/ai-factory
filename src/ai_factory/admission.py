"""
Admission and pacing: whether one more agent run may start now.

A scheduler asks `admit(key)` before it starts a run and calls `release(key)` when the run ends. The answer comes
from three things, all measured, none guessed:

- concurrency: at most `total` runs at once, and at most `per_key[key]` of one kind (a model, or a local GPU that
  serves one request at a time);
- back-off: after the provider says it is rate limited or overloaded (HTTP 429 / 529), no new run starts for a
  while -- `backoff_base_s`, doubling with each further one, up to `backoff_max_s`; a response that gets through
  ends the streak;
- plan usage: the claude CLI reports how much of each usage window (five hours, seven days) is used. No new run
  starts while a window is at `usage_cap` or more, or was refused outright, until that window resets; while the
  CLI warns about a window, only one run at a time.

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


@dataclass(frozen=True)
class Decision:
    ok: bool
    reason: str = ""      # why not: "concurrency", "per_key", "backoff", "usage", "refused", "warning"
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
    backoff_base_s: float = 30.0
    backoff_max_s: float = 900.0
    clock: Callable[[], float] = time.time

    def __post_init__(self):
        self.running: dict[str, int] = {}
        self.windows: dict[str, Window] = {}
        self.backoff_until = 0.0
        self.streak = 0
        self._lock = threading.Lock()

    # --- asking ------------------------------------------------------------------------------------------------
    def check(self, key: str) -> Decision:
        """What admit(key) would answer, without taking a slot."""
        now = self.clock()
        with self._lock:
            return self._decide(key, now)

    def admit(self, key: str) -> Decision:
        """May a run of `key` start now? When it may, it counts as running until release(key)."""
        now = self.clock()
        with self._lock:
            d = self._decide(key, now)
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

    def _decide(self, key: str, now: float) -> Decision:
        for name, w in self.windows.items():
            if w.resets_at and w.resets_at <= now:
                continue   # that window has reset: what we knew of it no longer holds
            if w.status == "rejected":
                return Decision(False, "refused", w.resets_at, f"the {name} usage limit is reached")
            if w.utilization >= self.usage_cap:
                return Decision(False, "usage", w.resets_at,
                                f"{name} usage at {w.utilization:.0%} (cap {self.usage_cap:.0%})")
        if self.backoff_until > now:
            return Decision(False, "backoff", self.backoff_until, "the provider said slow down (429/529)")
        n = sum(self.running.values())
        warned = [name for name, w in self.windows.items()
                  if w.status == "allowed_warning" and not (w.resets_at and w.resets_at <= now)]
        if warned and n >= 1:
            return Decision(False, "warning", 0.0, f"one at a time while {warned[0]} usage is high")
        if self.total is not None and n >= self.total:
            return Decision(False, "concurrency", 0.0, f"{n} running (limit {self.total})")
        limit = self.per_key.get(key)
        if limit is not None and self.running.get(key, 0) >= limit:
            return Decision(False, "per_key", 0.0, f"{key}: {self.running.get(key, 0)} running (limit {limit})")
        return Decision(True)

    # --- what the runs report ----------------------------------------------------------------------------------
    def observe(self, event: dict) -> None:
        """An agent run's stream event: `rate_limit` (plan usage), `api_retry` (429/529 back-off) or `call` (a
        response got through). Anything else is ignored."""
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

    def state(self) -> dict:
        """For a status line: what is running, the windows and any back-off."""
        with self._lock:
            return {"running": dict(self.running), "backoff_until": self.backoff_until,
                    "windows": {k: vars(w).copy() for k, w in self.windows.items()}}


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
