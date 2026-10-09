import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "shared"))
import forge_helper_files as helper_files  # noqa: E402


def test_plain_and_ultracode_workflow_helpers_are_both_found(tmp_path):
    sub = tmp_path / "sid" / "subagents"
    flow = sub / "workflows" / "wf_3b1d"
    flow.mkdir(parents=True)
    for folder, agent in ((sub, "a1"), (flow, "b2")):
        (folder / f"agent-{agent}.jsonl").write_text("{}\n")
        (folder / f"agent-{agent}.meta.json").write_text("{}")
    (flow / "journal.jsonl").write_text("{}\n")
    names = [Path(p).name for p in helper_files.transcripts(str(sub))]
    assert names == ["agent-a1.jsonl", "agent-b2.jsonl"]
    assert len(helper_files.metas(str(sub))) == 2
    assert helper_files.transcript(str(sub), "b2") == str(flow / "agent-b2.jsonl")
    assert helper_files.transcript(str(sub), "zz") is None
    assert helper_files.transcripts(str(tmp_path / "missing")) == []
