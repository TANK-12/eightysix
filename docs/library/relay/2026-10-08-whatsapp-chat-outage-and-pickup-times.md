# Relay WhatsApp chat: the 2026-10-08 outage and measured pickup times

date: 2026-10-08 · for: both

## The outage
- Dead 11:34 to 11:52 on Thu 2026-10-08: every chat launch failed with
  "No such file or directory: /tmp/pytest-of-ejb/pytest-34/test_clock_jump_back0".
- Cause: a critic's scratch test from Relay task 99 (`/tmp/critic99/t/test_critic.py`)
  used `tests/test_boss.py`'s fixture from outside `tests/`, so nothing set
  `RELAY_DATA_DIR` and the fixture wrote the real `settings.json`
  (`default_folder`, `poll_minutes` 0, `launch_gap_minutes` 0, `digest_time` 23:59).
- Fixed in Relay task 105 (commit 8b1491a and the WIP follow-up): tests
  can no longer reach the real data folder, a missing folder falls back to
  home, and a chat that cannot start tells him on WhatsApp and hands his
  messages to the boss line.

## Measured live (boss pid 185436, chat on default, opus medium, resumed)
| Test | Seen by the boss | Chat session started | Reply in WhatsApp |
|---|---|---|---|
| 12:32:30, after a quiet spell, default_folder pointed at a missing folder on purpose | 15.4 s | 15.5 s (in /home/ejb, the missing folder logged) | 20.6 s |
| 12:33, inside the 5-minute fast window | 1.8 s | 1.9 s | 9.5 s ("180 ■ ok") |

- Quiet poll is every 15 s (`whatsapp_poll_seconds`), fast poll every 2 s for
  5 minutes after his last message. The chat now starts in the same
  second the message is seen (before: up to the next one-minute tick).
