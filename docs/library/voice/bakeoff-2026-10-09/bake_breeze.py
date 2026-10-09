"""Breeze TTS 2 cases through 113's engine class (run with apps/voice/.venv/bin/python)."""
import json, sys, time, urllib.parse, wave
sys.path.insert(0, "/home/ejb/Forge/apps/voice")
import numpy as np
import service, engines
OUT = "/tmp/v120/bake/out"
EN_REF = service.models_home() / "voice/tts/breeze-tts-2/ref_voice.wav"
E1 = "Handler One to all units. The Legion are moving through the eastern sector, so hold your positions."
E2 = "I told you to fall back. Why didn't you listen to me?"
E3 = "You actually made it back. I really thought we had lost you out there."
reg = service.load_registry(); row = service.model_row(reg, "breeze-tts-2")
t0 = time.monotonic(); eng = engines.load(row, service.model_files(row), 6); load_s = time.monotonic() - t0
print("loaded in", round(load_s, 1), flush=True)
def gen(case, text, emotion, instruction=None, cfg=None):
    f = {"text": text, "voice_id": "harbour"}
    if instruction: f["instruction"] = instruction
    if cfg: f["cfg_scale"] = str(cfg)
    t = time.monotonic()
    pcm, h = eng._call("POST", "/v1/audio/speech", urllib.parse.urlencode(f).encode(), "application/x-www-form-urlencoded", timeout=600)
    dt = time.monotonic() - t
    rate = int(h.get("X-Sample-Rate") or 24000)
    a = np.frombuffer(pcm[: len(pcm) // 2 * 2], dtype="<i2").astype(np.float32) / 32768.0
    path = f"{OUT}/{case}.wav"; open(path, "wb").write(engines.wav_bytes(a, rate))
    rec = dict(model="breeze-tts-2", backend="vulkan", case=case, lang="en", text=text, emotion=emotion, ref=str(EN_REF), kind="clone",
               instruction=instruction, cfg=cfg, wall=round(dt, 2), wav=path, seconds=round(len(a) / rate, 2), rtf=round(dt / max(len(a) / rate, 0.01), 2))
    open("/tmp/v120/bake/results.jsonl", "a").write(json.dumps(rec) + "\n")
    print(case, rec["seconds"], "s in", rec["wall"], "RTF", rec["rtf"], flush=True)
try:
    gen("breeze_en_E1", E1, "neutral")
    gen("breeze_en_E2", E2, "neutral")
    gen("breeze_en_E2_angry", E2, "angry", "Speak angrily, frustrated and raising the voice.")
    gen("breeze_en_E2_sad", E2, "sad", "Speak sadly and quietly, close to tears.")
    gen("breeze_en_E2_whisper", E2, "whisper", "Whisper softly, as if someone might overhear.")
    gen("breeze_en_E3_laugh", "(laugh) " + E3, "laugh", None, 2.5)
    gen("breeze_en_E1_repeat", E1, "neutral")
finally:
    eng.close()
