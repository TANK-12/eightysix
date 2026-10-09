# Relay local chat: small-model benchmark

date: 2026-10-07 · for: both

Which small Jan model should answer Relay's WhatsApp chat when Claude is off
or out of usage (task 59). Measured on this laptop through Jan's llama.cpp
router on port 1337, CPU heavily contended (Godot bots running at ~167% CPU),
so absolute times are pessimistic; the ranking is what counts.

## Raw speed (one facts-heavy prompt, ~1.5k tokens in)

| model | prompt t/s | gen t/s | warm answer |
|---|---|---|---|
| qwen35-0_8b-spectralquant (Q4_K_M) | ~320 | ~39 | 5 s |
| Qwen3_5-2B-Uncensored (Q4_K_M) | ~215 | ~15 | 9 s |
| VibeThinker-3B (Q4_K_M) | ~107 | ~10 | 19-121 s, always emits `<think>`: unusable |
| Qwen3_5-4B (IQ4_XS) | 50-90 | 2.8-5.8 | 45 s warm, 205 s cold: too slow |

## Quality round (14 sample chats, `python localchat.py --bench`)

Samples live in `apps/relay/tests/localchat_samples.json` (status, usage,
CPU/GPU hogs, disk, Jan, stop a task, general knowledge, arithmetic, a
"fix the app" request it should decline).

| model | right | average time |
|---|---|---|
| 0.8B | 9/14 | 4.2 s |
| 2B | 12/14 | 15.3 s |

0.8B misses: wrong arithmetic (17x23 = "4,110"), invents a stop action on
the wrong task, echoes "stop task 61 please" instead of acting, vague GPU
answer. 2B misses: misreads the usage meter once, and wraps a disk answer in
a pointless `tell` action.

## Decision

Default is the **2B** (`DEFAULT_MODEL` in `apps/relay/localchat.py`): the
middle ground, clearly smarter than 0.8B and still well under the 4B's
45 s. Emerson can switch with `local model 0.8b` (fast) or `local model 4b`
on WhatsApp; the pick is a per-app Jan role (`relay` / `local`), his own Jan
settings are untouched.

Not checked: a bigger model he does not have. Candidates worth reviewing
before any install (none installed): Qwen3-4B-Instruct-2507 (non-thinking,
Q4_K_M ~2.5 GB), Gemma 3 4B-it, Llama 3.2 3B Instruct, Phi-4-mini-instruct
(3.8B). On this CPU any 3-4B will sit near the 4B's speed, so the 2B stays
the pick unless the GPU path gets used.

## Round 3: 2B `-long` copy, thinking off vs on (evening, 2026-10-07)

Same harness, 17 samples (3 new reasoning ones), quiet machine.

| setting | right | average time |
|---|---|---|
| thinking off | 12/17 | 9.4 s |
| thinking on | stopped after 1 sample | 175.6 s for "hey whats up" |

Writing ~15 tokens/s, reading ~169 tokens/s with thinking off. Thinking on
spends its whole budget reasoning before a one-line answer, so the run was
stopped (Emerson, 19:4x: "maybe we don't need thinking"). Decision: thinking
**off** by default (`local_thinking`), `think auto` / `think on` remain.

## Chat summaries (task 61), 2B, real chat stretches

Two stretches built from Emerson's real Wednesday chat (25 and 22
messages): 107 s and 81 s per summary. The first came out as 8 accurate
lines; the second ran past the 780-character limit, so the summariser now
keeps the first whole lines that fit (3 kept) instead of handing it to
Claude. Readable, a bit thin; Claude (Sonnet, low) still takes over when
Jan's summary is missing or fails the checks.
