"""A stand-in for `claude -p --input-format stream-json --output-format stream-json`.

Emits the same event shapes the real CLI does (checked against 2.1.270), so the
runner and the page can be tested without spending anything. Its command line
is written to $FAKE_CLAUDE_ARGS when set (with CLAUDE_CONFIG_DIR=<dir> as a
trailing entry when that variable is set). A message whose text is "slow"
makes it sit still until it is stopped; "crash" makes it exit with an error.
"busy" works for a second first; a message that arrives meanwhile is folded
into the same turn and answered in one reply, as the real CLI does.

`auth status --json` and `auth login` are faked too: the default config dir is
signed in as default@example.com; another CLAUDE_CONFIG_DIR is signed in once
`auth login` was fed the code "good-code#state" (any other code fails the way
the real CLI does).
"""

import json
import os
import select
import sys
import time
import uuid


def emit(event):
    sys.stdout.write(json.dumps(event) + "\n")
    sys.stdout.flush()


LOGIN_URL = "https://claude.com/cai/oauth/authorize?code=fake&state=fake"


def auth(args):
    config = os.environ.get("CLAUDE_CONFIG_DIR")
    marker = os.path.join(config, ".fake-login") if config else ""
    if args[:2] == ["auth", "status"]:
        email = "default@example.com" if not config else ""
        if marker and os.path.exists(marker):
            email = open(marker).read().strip()
        print(
            json.dumps(
                {
                    "loggedIn": bool(email),
                    "authMethod": "claude.ai" if email else "none",
                    "email": email,
                    "orgName": f"{email}'s Organization" if email else "",
                    "subscriptionType": "pro" if email else "",
                    "configDirectory": config or os.path.expanduser("~/.claude"),
                }
            )
        )
        return 0
    if args[:2] == ["auth", "login"]:
        sys.stdout.write(
            f"Opening browser to sign in…\nIf the browser didn't open, visit: {LOGIN_URL}\n"
            "Paste code here if prompted > "
        )
        sys.stdout.flush()
        code = sys.stdin.readline().strip()
        if code == "good-code#state" and marker:
            with open(marker, "w") as f:
                f.write("second@example.com")
            print("Logged in")
            return 0
        sys.stderr.write("Login failed: Request failed with status code 400\n")
        return 1
    sys.stderr.write("fake claude: unknown command\n")
    return 2


def main():
    args = sys.argv[1:]
    if args[:1] == ["auth"]:
        sys.exit(auth(args))
    if os.environ.get("FAKE_CLAUDE_ARGS"):
        logged = list(args)
        if os.environ.get("CLAUDE_CONFIG_DIR"):
            logged.append("CLAUDE_CONFIG_DIR=" + os.environ["CLAUDE_CONFIG_DIR"])
        for name in sorted(os.environ):  # the panel's agent limits
            if name.startswith(("CLAUDE_CODE_MAX_", "CLAUDE_CODE_SUBAGENT_")):
                logged.append(f"{name}={os.environ[name]}")
        with open(os.environ["FAKE_CLAUDE_ARGS"], "a") as f:
            f.write(json.dumps(logged) + "\n")
    session = (
        args[args.index("--resume") + 1] if "--resume" in args else str(uuid.uuid4())
    )
    emit(
        {
            "type": "system",
            "subtype": "init",
            "session_id": session,
            "model": "claude-fake",
            "tools": [],
            "slash_commands": ["verify", "clear", "mattpocock-skills:tdd"],
        }
    )
    turns = 0
    for line in sys.stdin:
        incoming = json.loads(line)
        if incoming.get("type") == "control_request":
            # the panel asks what the session's settings came to (ultracode)
            asked = "--settings" in args and json.loads(
                args[args.index("--settings") + 1]
            ).get("ultracode")
            emit(
                {
                    "type": "control_response",
                    "response": {
                        "subtype": "success",
                        "request_id": incoming["request_id"],
                        "response": {
                            "applied": {
                                "model": "claude-fake",
                                "ultracode": bool(asked),
                                "ultracodeRequested": bool(asked),
                                "ultracodeAvailable": True,
                            }
                        },
                    },
                }
            )
            continue
        message = incoming["message"]
        text = " ".join(
            b.get("text", "") for b in message["content"] if b["type"] == "text"
        )
        images = sum(1 for b in message["content"] if b["type"] == "image")
        with open(
            os.path.join(
                os.path.dirname(os.environ.get("FAKE_CLAUDE_ARGS") or "./x"),
                "inputs.jsonl",
            ),
            "a",
        ) as f:
            f.write(json.dumps(text) + "\n")
        if text.startswith("/compact"):  # as Claude Code 2.1.289 marks a compaction
            emit(
                {
                    "type": "system",
                    "subtype": "compact_boundary",
                    "compact_metadata": {"trigger": "manual", "pre_tokens": 1234},
                }
            )
        if text.startswith("[persona:"):  # the panel's per-message persona tag
            tag, _, text = text.partition("\n")
            with open(
                os.path.join(
                    os.path.dirname(os.environ.get("FAKE_CLAUDE_ARGS") or "./x"),
                    "tags.txt",
                ),
                "a",
            ) as f:
                f.write(tag + "\n")
        if text.startswith("slow"):
            time.sleep(60)
        if text.startswith("wait"):
            # Works a moment and does NOT fold in a message that arrives: the
            # real CLI when a message lands just as it ends the turn.
            time.sleep(0.4)
        if text.startswith("busy"):
            deadline = time.time() + 1.0
            while (left := deadline - time.time()) > 0:
                if select.select([sys.stdin], [], [], left)[0]:
                    extra = json.loads(sys.stdin.readline())["message"]["content"]
                    text += (
                        " + "
                        + " ".join(
                            b.get("text", "") for b in extra if b["type"] == "text"
                        ).split("\n")[-1]
                    )
        if text.startswith("crash"):
            sys.stderr.write("something broke\n")
            sys.exit(3)
        if "browser" in text:
            # A Forge Browser tool call and its result, as the real CLI streams them.
            tid = "toolu_" + uuid.uuid4().hex[:8]
            emit(
                {
                    "type": "assistant",
                    "message": {
                        "id": "msg_" + uuid.uuid4().hex[:8],
                        "role": "assistant",
                        "content": [
                            {
                                "type": "text",
                                "text": "Opening it in the Forge Browser.",
                            },
                            {
                                "type": "tool_use",
                                "id": tid,
                                "name": "mcp__forge-browser__open",
                                "input": {"url": "https://example.com/"},
                            },
                        ],
                    },
                }
            )
            emit(
                {
                    "type": "user",
                    "message": {
                        "role": "user",
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": tid,
                                "content": [
                                    {
                                        "type": "text",
                                        "text": '{"ok": true, "tab": {"title": "Example Domain"}}',
                                    }
                                ],
                            }
                        ],
                    },
                }
            )
        if text.startswith("pace"):
            # A long reply streamed word by word at about the real CLI's pace
            # (40 deltas a second), for tests/bench_stream_ui.py.
            count = int((text.split() + ["400"])[1])
            pid = "msg_" + uuid.uuid4().hex[:8]
            emit(
                {
                    "type": "stream_event",
                    "event": {"type": "message_start", "message": {"id": pid}},
                }
            )
            chunks = []
            for i in range(count):
                piece = (
                    f"\n\n- point {i} with **bold** and `code` "
                    if i % 25 == 0
                    else f"word{i} "
                )
                chunks.append(piece)
                emit(
                    {
                        "type": "stream_event",
                        "event": {
                            "type": "content_block_delta",
                            "index": 0,
                            "delta": {"type": "text_delta", "text": piece},
                        },
                    }
                )
                time.sleep(0.025)
            emit(
                {
                    "type": "assistant",
                    "message": {
                        "id": pid,
                        "role": "assistant",
                        "content": [{"type": "text", "text": "".join(chunks)}],
                    },
                }
            )
        if "SPLIT" in text:
            # The real CLI's shape: one reply id, one "assistant" event per
            # block, so an update is followed by a tool call in the same reply.
            sid = "msg_" + uuid.uuid4().hex[:8]
            emit(
                {
                    "type": "stream_event",
                    "event": {"type": "message_start", "message": {"id": sid}},
                }
            )
            emit(
                {
                    "type": "stream_event",
                    "event": {
                        "type": "content_block_delta",
                        "index": 0,
                        "delta": {"type": "text_delta", "text": "LIVE-FIRST update"},
                    },
                }
            )
            emit(
                {
                    "type": "assistant",
                    "message": {
                        "id": sid,
                        "role": "assistant",
                        "content": [{"type": "text", "text": "LIVE-FIRST update"}],
                    },
                }
            )
            emit(
                {
                    "type": "assistant",
                    "message": {
                        "id": sid,
                        "role": "assistant",
                        "content": [
                            {
                                "type": "tool_use",
                                "id": "toolu_split",
                                "name": "Bash",
                                "input": {"command": "true"},
                            }
                        ],
                    },
                }
            )
            emit(
                {
                    "type": "user",
                    "message": {
                        "role": "user",
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": "toolu_split",
                                "content": "ok",
                            }
                        ],
                    },
                }
            )
        if "PLAN" in text:
            # A plan and a todo list, as the real CLI sends them: ExitPlanMode
            # with the plan's markdown, then TodoWrite with every todo.
            pid = "msg_" + uuid.uuid4().hex[:8]
            todos = [
                {
                    "content": "Read the brief",
                    "status": "completed",
                    "activeForm": "Reading the brief",
                },
                {
                    "content": "Write the parser",
                    "status": "in_progress",
                    "activeForm": "Writing the parser",
                },
                {
                    "content": "Draw the star map",
                    "status": "pending",
                    "activeForm": "Drawing the star map",
                },
            ]
            for n, (name, tool_input) in enumerate(
                (
                    (
                        "ExitPlanMode",
                        {
                            "plan": "## Plan\n\n1. Read the brief\n2. Write the parser\n3. Draw the star map"
                        },
                    ),
                    ("TodoWrite", {"todos": todos}),
                )
            ):
                emit(
                    {
                        "type": "assistant",
                        "message": {
                            "id": pid,
                            "role": "assistant",
                            "content": [
                                {
                                    "type": "tool_use",
                                    "id": f"toolu_plan{n}",
                                    "name": name,
                                    "input": tool_input,
                                }
                            ],
                        },
                    }
                )
                emit(
                    {
                        "type": "user",
                        "message": {
                            "role": "user",
                            "content": [
                                {
                                    "type": "tool_result",
                                    "tool_use_id": f"toolu_plan{n}",
                                    "content": "ok",
                                }
                            ],
                        },
                    }
                )
        reply = (
            f"echo: {text} (images: {images})\n\n**Done.** See [the page](https://example.com/) "
            "and this code:\n\n```python\nprint('hi')\n```"
        )
        mid = "msg_" + uuid.uuid4().hex[:8]
        emit(
            {
                "type": "rate_limit_event",
                "rate_limit_info": {
                    "status": "allowed",
                    "resetsAt": 1789669200,
                    "rateLimitType": "five_hour",
                    "unifiedWindows": {
                        "five_hour": {"utilization": 0.42, "resetsAt": 1789669200},
                        "seven_day": {"utilization": 0.07, "resetsAt": 1790067600},
                    },
                },
            }
        )
        emit(
            {
                "type": "stream_event",
                "event": {"type": "message_start", "message": {"id": mid}},
            }
        )
        emit(
            {
                "type": "stream_event",
                "event": {
                    "type": "content_block_delta",
                    "index": 0,
                    "delta": {"type": "text_delta", "text": reply},
                },
            }
        )
        emit(
            {
                "type": "assistant",
                "message": {
                    "id": mid,
                    "role": "assistant",
                    "content": [{"type": "text", "text": reply}],
                },
            }
        )
        turns += 1
        emit(
            {
                "type": "result",
                "subtype": "success",
                "session_id": session,
                "total_cost_usd": round(0.001 * turns, 6),  # the running total
                "duration_ms": 5,
                "is_error": False,
            }
        )


if __name__ == "__main__":
    main()
