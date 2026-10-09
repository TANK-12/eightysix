"""Queue reporting. The worker itself is exercised by running real jobs; these
cover the arithmetic that is easy to get quietly wrong."""

import jobqueue


def _queue(tmp_path, jobs):
    """A real ResearchQueue over a temporary root, with its jobs replaced.

    Built through the actual constructor rather than __new__ so this does not
    silently miss state the queue gains later - which is exactly what happened
    when concurrent workers were added.
    """
    q = jobqueue.ResearchQueue(root=tmp_path)
    q.jobs = jobs
    return q


def job(name, phase, status, seconds=0.0):
    return {
        "id": name,
        "name": name,
        "slug": name.lower(),
        "entity_type": "person",
        "phase": phase,
        "qid": "",
        "prominence": 0,
        "country": "",
        "status": status,
        "added": "",
        "started": "",
        "finished": "",
        "seconds": seconds,
        "error": "",
        "changes": {},
    }


def test_a_deep_dive_does_not_wreck_the_estimate_for_quick_passes(tmp_path):
    """Seen for real: one 1253s deep dive in the history made 45 remaining
    quick passes read as eight hours instead of about forty minutes."""
    jobs = [
        job("deep-one", "deep", "done", 1253.0),
        job("trump", "quick", "done", 50.0),
    ]
    jobs += [job(f"q{i}", "quick", "queued") for i in range(45)]
    state = _queue(tmp_path, jobs).state()
    assert state["eta_seconds"] is not None
    minutes = state["eta_seconds"] / 60
    assert 30 < minutes < 60, f"estimate was {minutes:.0f} minutes"


def test_a_queued_deep_dive_is_costed_as_a_deep_dive(tmp_path):
    jobs = [
        job("deep-one", "deep", "done", 1200.0),
        job("q", "quick", "done", 60.0),
        job("next-deep", "deep", "queued"),
    ]
    state = _queue(tmp_path, jobs).state()
    assert state["eta_seconds"] == 1200


def test_an_empty_queue_has_no_estimate(tmp_path):
    state = _queue(tmp_path, [job("a", "quick", "done", 50.0)]).state()
    assert state["eta_seconds"] is None
    assert state["counts"]["done"] == 1


def test_jobs_are_ordered_running_then_queued_by_prominence(tmp_path):
    a, b, c = (
        job("a", "quick", "queued"),
        job("b", "quick", "queued"),
        job("c", "quick", "running"),
    )
    a["prominence"], b["prominence"] = 10, 300
    state = _queue(tmp_path, [a, b, c]).state()
    assert [j["name"] for j in state["jobs"]][:3] == ["c", "b", "a"]


def test_state_reports_concurrent_workers(tmp_path):
    q = _queue(tmp_path, [job("a", "quick", "queued")])
    state = q.state()
    assert "workers" in state and "in_flight" in state
    assert state["workers"] == 0 and state["in_flight"] == []


def test_several_subjects_can_be_in_flight_at_once(tmp_path):
    running = [job(f"r{i}", "quick", "running") for i in range(3)]
    q = _queue(tmp_path, running + [job("q1", "quick", "queued")])
    assert q.state()["counts"]["running"] == 3


def test_start_tops_up_a_depleted_pool(tmp_path, monkeypatch):
    """A worker that started while the queue was empty exited and was never
    replaced, leaving the whole run on one thread."""
    q = _queue(tmp_path, [])
    import threading

    alive = threading.Event()

    class _FakeThread:
        def __init__(self, *a, **kw):
            self._alive = True

        def start(self):
            alive.set()

        def is_alive(self):
            return self._alive

    monkeypatch.setattr(jobqueue.threading, "Thread", _FakeThread)
    q._threads = [_FakeThread()]  # one survivor
    q.start()
    assert len(q._threads) == jobqueue.WORKERS, "the pool was not brought back up"


# --- several queues, saved across a shutdown --------------------------------
#
# These cover the three things a long unattended run depends on: the queue file
# surviving a restart in the shape it went in, a pause meaning something the
# next morning, and work that is already done not being done twice.

import json

import dossier
import store


def hold_subject(tmp_path, name, depth="quick"):
    """Put a subject in the library the way a finished job would."""
    slug = store.slugify(name)
    d = store.ensure_subject(slug, tmp_path)
    store.write_json(
        d / dossier.FILES["subject"],
        {"slug": slug, "name": name, "entity_type": "person", "depth": depth},
    )
    return slug


def test_an_old_queue_file_migrates_without_losing_a_job(tmp_path):
    """The real file had 1,550 jobs in it. Losing any of them to a format
    change would be losing hours of finished research."""
    old = [job(f"s{i}", "quick", "queued") for i in range(50)]
    old += [job(f"d{i}", "quick", "done", 42.0) for i in range(7)]
    store.write_json(tmp_path / jobqueue.QUEUE_FILE, {"jobs": old, "saved": "then"})

    q = jobqueue.ResearchQueue(root=tmp_path)

    assert len(q.queues()) == 1
    assert q.active["name"] == jobqueue.DEFAULT_QUEUE_NAME
    assert len(q.jobs) == len(old)
    assert [j["id"] for j in q.jobs] == [j["id"] for j in old]
    assert sum(1 for j in q.jobs if j["status"] == "done") == 7


def test_migrating_keeps_a_copy_of_the_old_file(tmp_path):
    path = tmp_path / jobqueue.QUEUE_FILE
    store.write_json(path, {"jobs": [job("a", "quick", "queued")], "saved": "then"})
    jobqueue.ResearchQueue(root=tmp_path)._save()

    backup = path.with_name(path.name + jobqueue.BACKUP_SUFFIX)
    assert backup.is_file(), "the pre-migration file was not kept"
    assert json.loads(backup.read_text())["jobs"][0]["id"] == "a"


def test_a_pause_survives_the_app_closing(tmp_path):
    q = jobqueue.ResearchQueue(root=tmp_path)
    q.add("Someone")
    q.pause()

    reopened = jobqueue.ResearchQueue(root=tmp_path)
    assert reopened.state()["paused"] is True
    assert reopened.held() is True
    assert reopened.state()["counts"]["queued"] == 1


def test_the_memory_guard_does_not_clear_a_pause_the_user_set(tmp_path):
    """The guard pauses when memory runs short and lifts it again later. If it
    shared one flag with the user's pause, that lift would silently undo it."""
    q = jobqueue.ResearchQueue(root=tmp_path)
    q.pause()
    q.pause(by_guard=True)
    q.resume(by_guard=True)

    assert q.held() is True, "the guard's resume cleared the user's pause"
    assert jobqueue.ResearchQueue(root=tmp_path).state()["paused"] is True


def test_the_guards_hold_is_not_written_to_disk(tmp_path):
    q = jobqueue.ResearchQueue(root=tmp_path)
    q.pause(by_guard=True)
    assert q.held() is True
    assert jobqueue.ResearchQueue(root=tmp_path).state()["paused"] is False


def test_workers_only_see_the_active_queue(tmp_path):
    q = jobqueue.ResearchQueue(root=tmp_path)
    q.add("In the first queue")
    second = q.create_queue("Companies")
    q.activate(second["id"])

    assert q.jobs == []
    assert q._next() is None, "a worker reached into a queue that is not active"

    q.add("In the second queue")
    assert [j["name"] for j in q.jobs] == ["In the second queue"]
    assert len(jobqueue.ResearchQueue(root=tmp_path).queues()) == 2


def test_the_last_queue_cannot_be_deleted(tmp_path):
    q = jobqueue.ResearchQueue(root=tmp_path)
    assert q.delete_queue(q.active["id"]) is False
    assert len(q.queues()) == 1


def test_deleting_the_active_queue_activates_another(tmp_path):
    q = jobqueue.ResearchQueue(root=tmp_path)
    first = q.active["id"]
    second = q.create_queue("Second")
    q.activate(second["id"])
    assert q.delete_queue(second["id"]) is True
    assert q.active["id"] == first


# --- not doing work twice ---------------------------------------------------


def test_a_subject_already_held_is_skipped_rather_than_researched(tmp_path):
    hold_subject(tmp_path, "Angela Merkel")
    q = jobqueue.ResearchQueue(root=tmp_path)
    q.add("Angela Merkel")

    assert q._next() is None, "it picked up a subject that is already held"
    assert q.jobs[0]["status"] == "skipped"
    assert "already held" in q.jobs[0]["note"]


def test_a_subject_not_held_still_runs(tmp_path):
    q = jobqueue.ResearchQueue(root=tmp_path)
    q.add("Nobody Yet")
    picked = q._next()
    assert picked is not None and picked["name"] == "Nobody Yet"


def test_a_deep_dive_on_a_quick_held_subject_still_runs(tmp_path):
    """Deepening is the whole point of the 'Deepen held subjects' button, so
    skipping it as 'already held' would quietly break that feature."""
    hold_subject(tmp_path, "Angela Merkel", depth="quick")
    q = jobqueue.ResearchQueue(root=tmp_path)
    q.add("Angela Merkel", phase="deep")

    picked = q._next()
    assert picked is not None and picked["phase"] == "deep"


def test_a_deep_dive_on_an_already_deep_subject_is_skipped(tmp_path):
    hold_subject(tmp_path, "Angela Merkel", depth="deep")
    q = jobqueue.ResearchQueue(root=tmp_path)
    q.add("Angela Merkel", phase="deep")

    assert q._next() is None
    assert q.jobs[0]["status"] == "skipped"


def test_ticking_redo_researches_a_held_subject_again(tmp_path):
    hold_subject(tmp_path, "Angela Merkel")
    q = jobqueue.ResearchQueue(root=tmp_path)
    q.set_redo(q.active["id"], True)
    q.add("Angela Merkel")

    picked = q._next()
    assert picked is not None and picked["status"] == "running"


def test_skipping_a_run_of_subjects_writes_the_file_once(tmp_path):
    """A run can skip hundreds in a row and the queue file is large, so a save
    per skip would be a lot of writing to a USB drive for nothing."""
    for i in range(20):
        hold_subject(tmp_path, f"Held {i}")
    q = jobqueue.ResearchQueue(root=tmp_path)
    for i in range(20):
        q.add(f"Held {i}")

    writes = []
    real = store.write_json
    store.write_json = lambda p, payload: (writes.append(p), real(p, payload))[1]
    try:
        assert q._next() is None
    finally:
        store.write_json = real

    assert len(writes) == 1, f"wrote the queue file {len(writes)} times"
    assert all(j["status"] == "skipped" for j in q.jobs)


def test_skipped_jobs_do_not_break_the_status_ordering(tmp_path):
    """state() used to look statuses up in a bare dict, so an unknown one was
    a KeyError that took the whole Jobs tab down."""
    jobs = [job("a", "quick", "skipped"), job("b", "quick", "done", 5.0)]
    state = _queue(tmp_path, jobs).state()
    assert state["counts"]["skipped"] == 1
    assert [j["id"] for j in state["jobs"]] == ["a", "b"]


# --- honest counts ----------------------------------------------------------


def test_queueing_the_same_subject_twice_adds_one_job(tmp_path):
    q = jobqueue.ResearchQueue(root=tmp_path)
    first, made_first = q.add_job("Keir Starmer")
    second, made_second = q.add_job("Keir Starmer")

    assert made_first is True and made_second is False
    assert first["id"] == second["id"]
    assert len(q.jobs) == 1


def test_a_failed_job_is_retried_rather_than_left_alone(tmp_path):
    q = jobqueue.ResearchQueue(root=tmp_path)
    q.add("Keir Starmer")
    q.jobs[0]["status"] = "failed"

    _job, created = q.add_job("Keir Starmer")
    assert created is True, "a failure should be retryable by queueing again"


def test_a_second_press_reports_that_it_added_nothing(tmp_path, monkeypatch):
    """Pressing Queue twice used to say 'queued 148' both times while adding
    nothing the second time."""
    rows = [
        {"name": f"Subject {i}", "entity_type": "person", "qid": f"Q{i}"}
        for i in range(148)
    ]
    monkeypatch.setattr(jobqueue.seeds, "run_recipe", lambda *a, **k: list(rows))
    q = jobqueue.ResearchQueue(root=tmp_path)

    first = q.add_recipe("anything")
    second = q.add_recipe("anything")

    assert first["queued"] == 148 and first["already_queued"] == 0
    assert second["queued"] == 0 and second["already_queued"] == 148
    assert len(q.jobs) == 148


def test_seeding_follows_the_queues_own_redo_setting(tmp_path, monkeypatch):
    hold_subject(tmp_path, "Angela Merkel")
    rows = [{"name": "Angela Merkel", "entity_type": "person", "qid": "Q567"}]
    monkeypatch.setattr(jobqueue.seeds, "run_recipe", lambda *a, **k: list(rows))
    q = jobqueue.ResearchQueue(root=tmp_path)

    assert q.add_recipe("anything")["already_held"] == 1
    assert q.jobs == []

    q.set_redo(q.active["id"], True)
    assert q.add_recipe("anything")["queued"] == 1


# --- the other kinds of pass ------------------------------------------------


def test_an_images_job_is_not_judged_by_research_rules(tmp_path):
    """A subject already researched still needs its pictures fetching, so the
    'already held' rule must not swallow an images job."""
    slug = hold_subject(tmp_path, "Angela Merkel", depth="deep")
    store.write_json(
        store.subject_dir(slug, tmp_path) / dossier.FILES["images"],
        [{"kind": "portrait", "commons_file": "x.jpg", "url": "u", "stored": ""}],
    )
    q = jobqueue.ResearchQueue(root=tmp_path)
    q.add("Angela Merkel", phase="images")

    picked = q._next()
    assert picked is not None and picked["phase"] == "images"


def test_an_images_job_is_skipped_once_every_picture_is_downloaded(tmp_path):
    slug = hold_subject(tmp_path, "Angela Merkel")
    store.write_json(
        store.subject_dir(slug, tmp_path) / dossier.FILES["images"],
        [
            {
                "kind": "portrait",
                "commons_file": "x.jpg",
                "url": "u",
                "stored": "images/portrait-x.jpg",
            }
        ],
    )
    q = jobqueue.ResearchQueue(root=tmp_path)
    q.add("Angela Merkel", phase="images")

    assert q._next() is None
    assert q.jobs[0]["status"] == "skipped"


def test_a_tour_job_is_skipped_once_it_has_been_read(tmp_path, monkeypatch):
    hold_subject(tmp_path, "Angela Merkel")
    monkeypatch.setattr(
        jobqueue.speech_mod, "existing_tour", lambda *a, **k: "tour-x.mp3"
    )
    q = jobqueue.ResearchQueue(root=tmp_path)
    q.add("Angela Merkel", phase="tour")

    assert q._next() is None
    assert q.jobs[0]["note"] == "already read aloud"


def test_a_tour_job_runs_when_there_is_no_recording_yet(tmp_path, monkeypatch):
    hold_subject(tmp_path, "Angela Merkel")
    monkeypatch.setattr(jobqueue.speech_mod, "existing_tour", lambda *a, **k: "")
    q = jobqueue.ResearchQueue(root=tmp_path)
    q.add("Angela Merkel", phase="tour")

    picked = q._next()
    assert picked is not None and picked["phase"] == "tour"
