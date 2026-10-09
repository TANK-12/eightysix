# What Emerson's Claude use cost on 2026-10-07

date: 2026-10-07 · for: Emerson

## How it was counted

- Every Claude Code session log under `~/.claude/projects/`, from midnight AWST to about 21:20 AWST. That folder covers both accounts, default and hey; each message was counted once, by its message and request id.
- Prices are the API list prices from `docs/library/models/2026-09-30-model-benchmarks.md`, in US$ per million tokens:
  - Opus 5.5: $4 in, $20 out
  - Sonnet 5.5: $2 in, $10 out
  - Haiku 4.5: $1 in, $5 out
- Cache rates are fixed fractions of the input price:
  - Cache reads cost 0.1× input.
  - Cache writes that last 5 minutes cost 1.25×.
  - Cache writes that last 1 hour cost 2×.

## Tokens (measured)

| model | calls | output | cache read | cache write 1h | cache write 5m | list price |
|---|---|---|---|---|---|---|
| Opus 5.5 | 2797 | 1.69M | 293.4M | 4.57M | 4.71M | US$211.40 |
| Sonnet 5.5 | 137 | 0.04M | 4.9M | 0.48M | 0.07M | US$3.46 |
| Haiku 4.5 | 37 | 0.005M | 1.1M | 0.13M | 0 | US$0.39 |
| **total** | 2971 | 1.74M | 299.4M | 5.18M | 4.79M | **US$215.25** |

60 sessions. Uncached input was negligible: under 7k tokens.

## What it really cost Emerson

- Max 20x plan: US$200 a month, about US$6.60 a day.
- Laptop power: 15.9 W was measured on battery at about 21:20. A full 12-hour day at about 20 W is about 0.24 kWh. At a WA household rate of about A$0.32/kWh, that is roughly 8 cents. The rate is an estimate, not from his bill.
- Anthropic's own cost to serve these tokens is not published, so it is not estimated here.
