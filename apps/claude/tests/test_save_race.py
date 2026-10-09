"""Saves from parallel requests (the Enjoy task's three pickers post at once,
and FastAPI runs them on separate threads) must all land without an error."""

import threading

import runner


def test_parallel_saves_of_one_conversation_never_fail(tmp_path):
    conv = runner.Registry(tmp_path / "data").create()
    errors: list[BaseException] = []

    def save(n: int) -> None:
        for i in range(60):
            conv.meta[f"k{n}"] = i
            try:
                conv.save_meta()
            except Exception as e:  # noqa: BLE001  the test collects them
                errors.append(e)

    threads = [threading.Thread(target=save, args=(n,)) for n in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
