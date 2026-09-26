#!/usr/bin/env python3
"""A stand-in for `claude -p --output-format stream-json`: replays a scripted stream.

FAKE_CLAUDE_SCRIPT names a JSON file: {"lines": [...stream-json objects...], "argv_out": path, "stdin_out": path,
"sleep_before": seconds, "sleep_between": seconds, "exit": code, "stderr": text, "echo_steers": bool}.
With --input-format stream-json, user messages read from stdin are echoed back (isReplay) before the next line,
the way the real CLI takes a steer in at a tool boundary. A line {"$wait_for_steer": true} pauses until one arrives."""
import json
import os
import select
import sys
import time

script = json.load(open(os.environ["FAKE_CLAUDE_SCRIPT"]))
if script.get("argv_out"):
    json.dump(sys.argv[1:], open(script["argv_out"], "w"))
streamed = "--input-format" in sys.argv
stdin_seen = []


def take_steers(block: bool = False) -> None:
    while True:
        ready, _, _ = select.select([sys.stdin], [], [], 5 if block else 0)
        if not ready:
            return
        line = sys.stdin.readline()
        if not line:
            return
        stdin_seen.append(line)
        msg = json.loads(line)
        print(json.dumps({"type": "user", "isReplay": True, "uuid": msg.get("uuid"),   # taken in: echoed
                          "message": msg.get("message")}), flush=True)
        if block:
            return


if not streamed:
    stdin_seen.append(sys.stdin.read())
else:
    stdin_seen.append(sys.stdin.readline())
time.sleep(script.get("sleep_before", 0))
for obj in script["lines"]:
    if streamed and script.get("echo_steers", True):
        take_steers(block=obj.get("$wait_for_steer", False))
    if "$wait_for_steer" in obj:
        continue
    print(json.dumps(obj), flush=True)
    time.sleep(script.get("sleep_between", 0))
if script.get("stdin_out"):
    json.dump(stdin_seen, open(script["stdin_out"], "w"))
if script.get("stderr"):
    sys.stderr.write(script["stderr"])
sys.exit(script.get("exit", 0))
