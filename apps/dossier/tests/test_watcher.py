"""The news watcher.

The rules that matter here are the ones about not trampling the user: a sweep
must never clear a pause, never shoulder past work already queued, and never
override the memory guard. Those are checked against a stub queue that records
what it was asked to do.
"""

import dossier
import store
import watcher


def hold(tmp_path, name, updated, entity_type="person"):
    slug = store.slugify(name)
    d = store.ensure_subject(slug, tmp_path)
    store.write_json(
        d / dossier.FILES["subject"],
        {
            "slug": slug,
            "name": name,
            "entity_type": entity_type,
            "depth": "quick",
            "updated": updated,
        },
    )
    dossier.reindex(tmp_path)
    return slug


class StubQueue:
    """Enough of ResearchQueue to see what the watcher does to it."""

    def __init__(self, paused=False, guard_hold=False, counts=None):
        self._state = {
            "paused": paused,
            "guard_hold": guard_hold,
            "counts": counts or {},
            "active_queue": {"id": "q1", "name": "Main"},
        }
        self._queues = [{"id": "q1", "name": "Main"}]
        self.added = []
        self.started = False
        self.activated = None

    def state(self):
        return self._state

    def queues(self):
        return list(self._queues)

    def create_queue(self, name, redo_held=False):
        made = {"id": "w1", "name": name, "redo_held": redo_held}
        self._queues.append(made)
        return made

    def activate(self, queue_id):
        self.activated = queue_id
        return True

    def add_job(self, name, entity_type="person", phase="quick"):
        self.added.append((name, entity_type, phase))
        return {"name": name}, True

    def start(self):
        self.started = True


# --- picking what to refresh ------------------------------------------------


def test_the_stalest_subjects_come_first(tmp_path):
    hold(tmp_path, "Fresh", "2026-09-10T00:00:00+00:00")
    hold(tmp_path, "Stale", "2026-01-01T00:00:00+00:00")
    hold(tmp_path, "Middling", "2026-06-01T00:00:00+00:00")
    assert [r["name"] for r in watcher.stale(3, tmp_path)] == [
        "Stale",
        "Middling",
        "Fresh",
    ]


def test_a_subject_with_no_timestamp_is_the_stalest_of_all(tmp_path):
    """It predates the field, so it has not been looked at in longer."""
    hold(tmp_path, "Dated", "2026-01-01T00:00:00+00:00")
    hold(tmp_path, "Undated", "")
    assert watcher.stale(1, tmp_path)[0]["name"] == "Undated"


# --- not trampling the user -------------------------------------------------


def test_a_sweep_does_not_clear_a_pause(tmp_path):
    hold(tmp_path, "Someone", "")
    watcher.update({"enabled": True}, tmp_path)
    queue = StubQueue(paused=True)
    result = watcher.sweep(queue, tmp_path)
    assert result["ran"] is False
    assert "paused" in result["reason"]
    assert queue.started is False and queue.added == []


def test_a_sweep_waits_for_work_already_queued(tmp_path):
    hold(tmp_path, "Someone", "")
    watcher.update({"enabled": True}, tmp_path)
    queue = StubQueue(counts={"queued": 40})
    result = watcher.sweep(queue, tmp_path)
    assert result["ran"] is False and queue.added == []


def test_a_sweep_respects_the_memory_guard(tmp_path):
    hold(tmp_path, "Someone", "")
    watcher.update({"enabled": True}, tmp_path)
    queue = StubQueue(guard_hold=True)
    result = watcher.sweep(queue, tmp_path)
    assert result["ran"] is False and "memory guard" in result["reason"]


def test_a_deferred_sweep_is_not_recorded_as_having_happened(tmp_path):
    """Otherwise the clock would restart and the refresh would be skipped."""
    hold(tmp_path, "Someone", "")
    watcher.update({"enabled": True}, tmp_path)
    watcher.sweep(StubQueue(paused=True), tmp_path)
    assert watcher.settings(tmp_path)["last_sweep"] == ""
    assert watcher.due(tmp_path) is True


def test_switched_off_means_off(tmp_path):
    hold(tmp_path, "Someone", "")
    result = watcher.sweep(StubQueue(), tmp_path)
    assert result["ran"] is False and result["queued"] == 0


# --- what a sweep actually does ---------------------------------------------


def test_a_sweep_queues_quick_passes_into_its_own_redo_queue(tmp_path):
    hold(tmp_path, "A", "2026-01-01T00:00:00+00:00")
    hold(tmp_path, "B", "2026-02-01T00:00:00+00:00")
    watcher.update({"enabled": True, "per_sweep": 2}, tmp_path)
    queue = StubQueue()
    result = watcher.sweep(queue, tmp_path)
    assert result["ran"] is True and result["queued"] == 2
    assert [a[2] for a in queue.added] == ["quick", "quick"]
    assert queue.started is True
    # Refreshing a held subject IS the job, so the queue must redo held ones
    # or every sweep would queue subjects and then skip all of them.
    made = [q for q in queue.queues() if q["name"] == watcher.QUEUE_NAME][0]
    assert made["redo_held"] is True
    assert queue.activated == made["id"]


def test_the_sweep_is_recorded_and_the_clock_restarts(tmp_path):
    hold(tmp_path, "A", "")
    watcher.update({"enabled": True, "every_hours": 6}, tmp_path)
    watcher.sweep(StubQueue(), tmp_path)
    config = watcher.settings(tmp_path)
    assert config["last_sweep"] and config["sweeps"][0]["queued"] == 1
    assert watcher.due(tmp_path) is False


def test_settings_survive_and_are_clamped(tmp_path):
    watcher.update({"enabled": True, "every_hours": 9999, "per_sweep": 0}, tmp_path)
    config = watcher.settings(tmp_path)
    assert config["every_hours"] == 168 and config["per_sweep"] == 1
    assert config["enabled"] is True


def test_changing_a_setting_keeps_the_history(tmp_path):
    hold(tmp_path, "A", "")
    watcher.update({"enabled": True}, tmp_path)
    watcher.sweep(StubQueue(), tmp_path)
    watcher.update({"per_sweep": 30}, tmp_path)
    assert len(watcher.settings(tmp_path)["sweeps"]) == 1


def test_run_scheduled_does_nothing_until_due(tmp_path):
    hold(tmp_path, "A", "")
    watcher.update({"enabled": True}, tmp_path)
    watcher.sweep(StubQueue(), tmp_path)
    assert watcher.run_scheduled(StubQueue(), tmp_path)["ran"] is False


def test_state_names_what_is_next_and_what_is_freshest(tmp_path):
    hold(tmp_path, "Old", "2026-01-01T00:00:00+00:00")
    hold(tmp_path, "New", "2026-09-01T00:00:00+00:00")
    watcher.update({"enabled": True, "per_sweep": 1}, tmp_path)
    payload = watcher.state(StubQueue(), tmp_path)
    assert payload["next_up"][0]["name"] == "Old"
    assert payload["freshest"][0]["name"] == "New"
    assert payload["held"] == 2
