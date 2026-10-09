"""When anything gets said: one background thread, and the only caller of Jan.

The simulation ticks ten times a second and must never wait for a model, so
every model call happens here instead, on a thread of its own. The world is
only ever touched through its own lock, so a conversation arriving mid-tick
cannot catch a crew member half-moved.

What it decides, in priority order:

1. A time-skip that is waiting for its paragraph -- you are standing there
   reading "6 hours passed while you were away", so this comes first.
2. A new station day that has not been narrated.
3. A conversation, if one is due.

What stops it:

* the away mode, through `world.models_allowed()`. "Idle when closed" means the
  crew keep to their day with the tab shut and nobody speaks until you return;
  that rule lives in sim.py and is simply obeyed here.
* the chatter setting, including "off", which is a level like any other.
* Jan being absent. Failures back off from 5 seconds to two minutes rather than
  hammering a server that is not there, and recover on the first success.
"""

from __future__ import annotations

import random
import threading
import time

from . import chatter, narrator, player as player_module

# How long between checks. Short enough that a due conversation starts promptly,
# long enough to cost nothing.
BEAT = 1.0
BACKOFF_START = 5.0
BACKOFF_MAX = 120.0


class Director:
    def __init__(self, world, client, seed=None, log=print):
        self.world = world
        self.client = client
        self.log = log
        self.rng = random.Random(seed)
        self.next_conversation = 0.0
        self.next_greeting = 0.0
        self.backoff = 0.0
        self.failures = 0
        self.busy = False
        self.last_reason = "starting"
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    # --- when to speak ------------------------------------------------------

    def interval(self):
        """Seconds between conversations, from the chatter setting. Zero means
        the crew are quiet on purpose."""
        from . import sim

        level = sim.CHATTER_LEVELS.get(
            self.world.settings.get("chatter"), sim.CHATTER_LEVELS["moderate"]
        )
        per_minute = float(level.get("per_minute", 1.0))
        if per_minute <= 0:
            return 0.0
        return 60.0 / per_minute

    def due(self, now):
        gap = self.interval()
        if gap <= 0:
            return False
        if not self.next_conversation:
            # Spread the first one out a little so the station does not open
            # with everybody talking at once.
            self.next_conversation = now + self.rng.uniform(2.0, gap)
            return False
        return now >= self.next_conversation

    def schedule_next(self, now):
        gap = self.interval()
        jitter = self.rng.uniform(0.75, 1.35)
        self.next_conversation = now + max(5.0, gap * jitter)

    # --- one pass -----------------------------------------------------------

    def step(self, now=None):
        """One decision. Returns what it did, which is what the tests assert on."""
        now = time.monotonic() if now is None else now
        if self.backoff and now < self.backoff:
            return "backing off"
        if self.interval() <= 0:
            # Crew chatter is off, and that means off: no conversations, no
            # narrator, nothing loaded. The two buttons in the settings pane
            # still work, because pressing one is asking for it.
            self.last_reason = "voices are off"
            return "voices off"
        if not self.world.models_allowed():
            self.last_reason = "away mode says no models right now"
            return "not allowed"

        summary = self.world.pending_summary
        if summary and summary.get("needs_narrator"):
            return self.run(self.narrate_skip, "time-skip summary")
        if self.world.take_new_day():
            return self.run(self.narrate_day, "the day's event")
        player = self.world.player
        if player.aboard and not player.named:
            return self.run(self.name_the_player, "naming the new arrival")
        if player.aboard and now >= self.next_greeting:
            # Someone you walked past says hello. Spaced out on its own timer so
            # standing in a busy mess hall is not a wall of greetings.
            self.next_greeting = now + self.rng.uniform(25.0, 70.0)
            if player_module.bystanders(self.world):
                return self.run(self.greet, "a greeting")
        if self.due(now):
            self.schedule_next(now)
            return self.run(self.talk, "a conversation")
        return "waiting"

    def run(self, job, what):
        self.busy = True
        self.last_reason = what
        try:
            job()
            self.failures = 0
            self.backoff = 0.0
            return what
        except Exception as exc:  # a model failure must never stop the station
            self.failures += 1
            wait = min(BACKOFF_MAX, BACKOFF_START * (2 ** (self.failures - 1)))
            self.backoff = time.monotonic() + wait
            self.world.note_model_problem(f"{type(exc).__name__}: {exc}")
            self.log(f"[janhollow] {what} failed ({exc}); waiting {wait:.0f}s")
            return f"{what} failed"
        finally:
            self.busy = False

    # --- the jobs -----------------------------------------------------------

    def talk(self):
        chatter.converse(self.world, self.client, self.rng)

    def narrate_day(self):
        story = narrator.day_event(self.world, self.client, self.rng)
        if story:
            self.world.set_day_story(story)
            self.world.remember_everyone(story["story"])

    def name_the_player(self):
        """Who you turned out to be. Runs once, after you are already walking
        around, because a thirty-second model call is no way to start a game."""
        found = narrator.name_the_arrival(self.world, self.client, self.rng)
        player = self.world.player
        with self.world.lock:
            player.named = True  # one attempt; a failure leaves you unnamed
            if found:
                player.name = found["name"]
                player.role = found.get("role", "")
                player.arrival = found.get("arrival", "")
                self.world.model_status["narrator_runs"] += 1
                self.world.note(
                    f"{player.name} came aboard — {player.role}. {player.arrival}",
                    kind="story",
                )

    def greet(self):
        near = player_module.bystanders(self.world)
        if not near:
            return
        member = self.rng.choice(near)
        line = chatter.greet_player(self.world, self.client, member, self.rng)
        if line:
            self.world.say(member.id, line, chatter.BUBBLE_SECONDS)

    def answer_player(self, text):
        """Your line, and one crew member's answer. Runs on the request rather
        than the worker: you are standing there waiting for it."""
        member = player_module.nearest_crew(self.world)
        if not member:
            return None
        self.world.say(self.world.player.id, text, chatter.BUBBLE_SECONDS)
        line, was_fallback = chatter.reply_to_player(
            self.world, self.client, member, text, self.rng
        )
        self.world.say(member.id, line, chatter.BUBBLE_SECONDS)
        with self.world.lock:
            warmth = int(member.relationships.get(self.world.player.id, 0))
            member.relationships[self.world.player.id] = min(3, warmth + 1)
            member.memories.append(f"{self.world.player.name} said: {text}")
            del member.memories[:-12]
        return {
            "who": member.record.get("label", member.id),
            "id": member.id,
            "line": line,
            "fallback": was_fallback,
        }

    def narrate_skip(self):
        summary = dict(self.world.pending_summary or {})
        story = narrator.time_skip_story(self.world, self.client, summary, self.rng)
        with self.world.lock:
            current = self.world.pending_summary
            if not current:
                return
            current["needs_narrator"] = False
            if story:
                current["story"] = story
                self.world.model_status["narrator_runs"] += 1
                self.world.note(story, kind="story")

    # --- the thread ---------------------------------------------------------

    def start(self):
        if self._thread:
            return self._thread

        def loop():
            while not self._stop.wait(BEAT):
                try:
                    self.step()
                except Exception as exc:
                    self.log(f"[janhollow] director: {type(exc).__name__}: {exc}")

        self._thread = threading.Thread(
            target=loop, daemon=True, name="janhollow-voices"
        )
        self._thread.start()
        return self._thread

    def stop(self):
        self._stop.set()

    def status(self):
        return {
            "busy": self.busy,
            "doing": self.last_reason,
            "failures": self.failures,
            "backing_off": max(0.0, self.backoff - time.monotonic()),
            "seconds_to_next": max(0.0, self.next_conversation - time.monotonic()),
            "jan": dict(self.client.stats),
        }
