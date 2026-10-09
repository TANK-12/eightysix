def test_pick_group_prefers_the_wanted_scan_group():
    from panelforge.library.fetch import pick_group

    rows = [
        {"number": 1.0, "group": "Asura Scans", "url": "a1"},
        {"number": 1.0, "group": "WebToon", "url": "w1"},
        {"number": 2.0, "group": "Asura Scans", "url": "a2"},
        {"number": 3.0, "group": "WebToon", "url": "w3"},
        {"number": 3.0, "group": "Asura Scans", "url": "a3"},
    ]
    logs = []

    class J:
        def log(self, m):
            logs.append(m)

    got = pick_group(rows, "WebToon", J())
    assert [c["url"] for c in got] == ["w1", "a2", "w3"]
    assert logs and "1 chapter(s) have no 'WebToon'" in logs[0]
    assert [c["url"] for c in pick_group(rows, None)] == ["a1", "a2", "w3"]
