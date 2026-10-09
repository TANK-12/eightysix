# Claude model benchmarks and which to use
date: 2026-09-30 · for: both

Figures copied from anthropic.com/claude-sonnet-5-5 and the platform models
overview, read 2026-09-30. Rules built on them: ~/Forge/shared/model_advice.json
(skill: model-pick).

| Benchmark | Sonnet 5.5 | Opus 5.5 | Sonnet 5 |
|---|---|---|---|
| Terminal-Bench 4.0 (agentic coding in a terminal) | 70.6% | 66.4% | 10.3% |
| FrontierCode 1.1 (hard coding) | 46.2% (max effort) | 54.4% | 42.4% |
| CursorBench 4.0 (editor coding) | 55.5% | 57.8% | 34.1% |
| GDPval-AA v2.1 (knowledge work, Elo) | 1844 | 1846 | 1449 |
| AA-Briefcase v1.1 (knowledge work, Elo) | 1811 | 1822 | 1359 |
| Humanity's Last Exam (with tools) | 64.5% | 67.7% | 54.9% |
| OSWorld 2.1 (computer use) | 80.1% | 81.8% | 57.0% |
| Chartography (reading charts, no tools) | 61.6% | 64.4% | 15.6% |

Price per million tokens in/out: Haiku 4.5 $1/$5 · Sonnet 5.5 $2/$10 ·
Opus 5.5 $4/$20 · Fable 5.1 $10/$50. Context: 1M tokens for Sonnet 5.5,
Opus 5.5 and Fable 5.1; 200k for Haiku 4.5. Speed: Haiku fastest, Sonnet fast,
Opus moderate, Fable slower. Default effort in Claude Code: medium.

Anthropic's own words: Sonnet 5.5 "is strongest at well-scoped everyday tasks,
fixing bugs, and creating polished documents"; Opus 5.5 "remains clearly
stronger at complex, open-ended work requiring sustained judgment". Fable 5.1
is for "demanding reasoning and long-horizon agentic work".

Reasoned (not measured on this laptop): on the subscription, Opus uses the
5-hour window about twice as fast as Sonnet, going by the price ratio.

## Other people's benchmarks (read the same day)

| Test (who ran it) | Sonnet 5.5 | Opus 5.5 |
|---|---|---|
| Intelligence Index (Artificial Analysis), max effort | 56 | 58 |
| same, Sonnet at xhigh / high / medium | 52 / 47 / 41 | not published |
| SWE-bench Pro (real repo fixes, BenchLM/Morph) | 81.3% | 89.9% |
| Coding aggregate (BenchLM) | 85.1 | 83.6 |
| Code review, bugs caught of 13 (CodeRabbit) | 6 | 8 (standard), 10 (max) |
| Code review, comments worth acting on (CodeRabbit) | 41.2% | 66.7% (standard) |
| Factual recall, AA-Omniscience | 54% | 66% |
| Hallucination rate, AA-Omniscience (lower is better) | 47% | 59% |
| Cost per review (CodeRabbit) | $0.47 | about $1.17 |

Also: Sonnet 5.5 is very wordy at high effort (about 193k output tokens per
index task at max; 410M tokens for the whole index vs a median of 81M), so its
cost per task is only about 30% below Opus (The Decoder, VentureBeat), not
half. Rules changed on this: everyday code work runs Sonnet at high, not
medium; reviews, bug hunts and fact research go to Opus high; Sonnet never
above high (step up to Opus instead).
