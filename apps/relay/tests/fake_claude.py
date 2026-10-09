#!/usr/bin/env python3
"""Stands in for `claude -p` in the boss tests. The request text in the task
file picks the behaviour: FAKE:done, FAKE:continue, FAKE:blocked, FAKE:error,
FAKE:sleep; HANDOFF:done|blocked|quiet picks what a hand-over turn
writes (it writes continue without one). A planning prompt makes it write one new task file.
A review prompt answers REVIEW:continue|park|none|error|limit|sleep (continue
without one).
"""

import json
import os
import re
import sys
import time

prompt = sys.stdin.read()
with open(os.environ["FAKE_LOG"], "a") as log:
    log.write(
        json.dumps(
            {
                "argv": sys.argv[1:],
                "prompt": prompt[:3000],
                "config": os.environ.get("CLAUDE_CONFIG_DIR", ""),
                "run_id": os.environ.get("RELAY_RUN_ID", ""),
            }
        )
        + "\n"
    )


def say(event):
    print(json.dumps(event), flush=True)


say({"type": "system", "subtype": "init"})
say(
    {
        "type": "assistant",
        "message": {
            "usage": {
                "input_tokens": 5,
                "cache_read_input_tokens": 20000,
                "output_tokens": 50,
            },
            "content": [
                {"type": "tool_use", "name": "Bash", "input": {"command": "ls"}}
            ],
        },
    }
)
plan = re.search(r"markdown files in (\S+)/, named", prompt)
if plan:
    with open(os.path.join(plan.group(1), "new-step.md"), "w") as fh:
        fh.write("# Planned step\n\n## Request\n\nFAKE:done\n")
    say({"type": "result", "is_error": False, "result": "Planned one task."})
    sys.exit(0)
review = re.search(r"Relay's reviewer for task .*?\nTask file: (\S+\.md)", prompt, re.S)
if review:
    asked = re.search(r"REVIEW:(\w+)", open(review.group(1)).read())
    verdict = asked.group(1) if asked else "continue"
    if verdict == "sleep":  # a review that runs on until the boss cuts it off
        time.sleep(60)
    if verdict in ("error", "limit"):
        why = (
            "API Error: 500 boom"
            if verdict == "error"
            else "Claude AI usage limit reached"
        )
        say({"type": "result", "is_error": True, "result": why})
        sys.exit(1)
    answer = (
        "I could not tell."
        if verdict == "none"
        else (f"Looked at it.\n**Verdict:** {verdict} - fake reason for {verdict}")
    )
    say({"type": "result", "is_error": False, "result": answer})
    sys.exit(0)
found = re.search(
    r"(?:task file: |State section of |Your file: |Notes go in )(\S+\.md)", prompt
)
assert found, "no task file in the prompt"
path = found.group(1)
text = open(path).read()
wanted = re.search(r"FAKE:(\w+)", text)
mode = wanted.group(1) if wanted else "done"
if "--resume" in sys.argv and "stop now" in prompt:
    after = re.search(r"HANDOFF:(\w+)", text)
    mode = f"handoff_{after.group(1)}" if after else "handoff"
if mode == "handoff_quiet":  # a hand-over turn that leaves the file alone
    say({"type": "result", "is_error": False, "result": "Stopped."})
    sys.exit(0)
if mode == "sleep":
    time.sleep(60)
if mode == "error":
    say({"type": "result", "is_error": True, "result": "API Error: 500 boom"})
    sys.exit(1)
if mode == "limit":
    say({"type": "result", "is_error": True, "result": "Claude AI usage limit reached"})
    sys.exit(1)
status = {
    "done": "done",
    "continue": "continue",
    "blocked": "blocked: need the password",
    "handoff": "continue",
    "handoff_done": "done",
    "handoff_blocked": "blocked: need the password",
}[mode]
with open(path, "a") as fh:
    fh.write(f"- worked\n- status: {status}\n")
say(
    {
        "type": "result",
        "is_error": False,
        "result": f"Report: {mode}",
        "total_cost_usd": 0.5,
    }
)
