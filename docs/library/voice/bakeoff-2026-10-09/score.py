"""Score results.jsonl: SenseVoice transcript + emotion/event tags (CPU server), WER/CER, speaker SIM.
Writes scores.jsonl and prints a compact table."""
import json, re, subprocess, sys, unicodedata
sys.path.insert(0, "/tmp/v120/bake")
import ac
recs = [json.loads(l) for l in open("/tmp/v120/bake/results.jsonl") if l.strip()]
recs = [r for r in recs if r.get("wav") and r.get("seconds", 1) > 0]
TAG = re.compile(r"<\|([^|]+)\|>")
EMO = {"HAPPY", "SAD", "ANGRY", "NEUTRAL", "FEARFUL", "DISGUSTED", "SURPRISED", "EMO_UNKNOWN"}
def clean(t):
    t = re.sub(r"\[[^\]]*\]|\([^)]*\)", " ", t)
    t = "".join(c for c in t if not unicodedata.category(c).startswith(("S", "P")) or c == "'")
    return t.lower().replace("'", "")
def edits(a, b):
    d = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        p, d[0] = d[0], i
        for j, y in enumerate(b, 1):
            p, d[j] = d[j], min(d[j] + 1, d[j - 1] + 1, p + (x != y))
    return d[len(b)]
def err_rate(ref, hyp, lang):
    r, h = clean(ref), clean(hyp)
    if lang == "ja":
        r, h = r.replace(" ", ""), h.replace(" ", "")
        return edits(list(r), list(h)) / max(len(r), 1)
    r, h = r.split(), h.split()
    return edits(r, h) / max(len(r), 1)
s = ac.Server(backend="cpu", log="/tmp/v120/bake/score_server.log")
try:
    for r in recs:
        body = {"model": "sensevoice", "audio": r["wav"], "language": r["lang"], "options": {"keep_tags": True, "enable_itn": True, "audio_chunk_mode": "none"}}
        resp, dt, err = s.post("/v1/audio/transcriptions", body)
        if err:
            r["asr_err"] = err; continue
        txt = json.loads(resp[0]).get("text", "")
        tags = TAG.findall(txt)
        r["heard"] = TAG.sub("", txt).strip()
        r["emo_heard"] = [t for t in tags if t in EMO]
        r["events"] = [t for t in tags if t not in EMO and t.lower() not in ("en", "ja", "zh", "withitn", "speech", "woitn")]
        r["err_rate"] = round(err_rate(r["text"], r["heard"], r["lang"]), 3)
finally:
    s.close()
by_ref = {}
for r in recs:
    if r.get("ref"): by_ref.setdefault(r["ref"], []).append(r["wav"])
for ref, wavs in by_ref.items():
    out = subprocess.run(["/tmp/v120/simvenv/bin/python", "/tmp/v120/bake/sim.py", ref, *wavs], capture_output=True, text=True)
    sims = json.loads(out.stdout.strip().splitlines()[-1])
    for r in recs:
        if r.get("ref") == ref: r["sim"] = sims.get(r["wav"])
with open("/tmp/v120/bake/scores.jsonl", "w") as f:
    for r in recs: f.write(json.dumps(r, ensure_ascii=False) + "\n")
for r in recs:
    print(f"{r['case']:<24} {r.get('seconds',0):>5.2f}s RTF {r.get('rtf',0):>5.2f} err {r.get('err_rate','?')!s:<6} sim {r.get('sim','?')!s:<6} emo {','.join(r.get('emo_heard',[]))} ev {','.join(r.get('events',[]))} | {r.get('heard', r.get('asr_err',''))[:70]}")
