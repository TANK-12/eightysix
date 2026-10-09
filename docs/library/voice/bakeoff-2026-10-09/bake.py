"""Relay 120 bake-off: generate every case for one model group, log timings to results.jsonl.
usage: bake.py <group> [backend]   group: irodori | auk | omni"""
import json, sys, time, os
sys.path.insert(0, "/tmp/v120/bake")
import ac
OUT = "/tmp/v120/bake/out"; os.makedirs(OUT, exist_ok=True)
EN_REF = ac.M + "/tts/breeze-tts-2/ref_voice.wav"
EN_REF_TEXT = "The harbour lights came on one by one as the evening tide began to turn."
JA_REF = OUT + "/ja_ref_irodori_vdes.wav"
JA_REF_TEXT = "こちらハンドラー・ワン。本日より、皆さんの指揮を担当します。よろしくお願いします。"
E1 = "Handler One to all units. The Legion are moving through the eastern sector, so hold your positions."
E2 = "I told you to fall back. Why didn't you listen to me?"
E3 = "You actually made it back. I really thought we had lost you out there."
J1 = "ハンドラー・ワンより全機へ。レギオンが東部戦区を移動中です。持ち場を維持してください。"
J2 = "下がれと言ったはずです。どうして聞いてくれなかったんですか。"
J3 = "本当に戻ってきたんですね。もう会えないかと思っていました。"
SEED = 42

def en_dur(t): return round(0.38 * len(t.split()) + 0.5, 2)
def ja_dur(t): return round(len([c for c in t if c not in "。、・？！"]) / 7.0 + 0.5, 2)

def log(rec):
    with open("/tmp/v120/bake/results.jsonl", "a") as f: f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(rec.get("case"), rec.get("err") or f"{rec['seconds']:.2f}s audio in {rec['wall']:.1f}s RTF {rec['rtf']:.2f}", flush=True)

def run(s, case, path, body, meta):
    r, dt, err = s.post(path, body)
    rec = dict(meta, case=case, wall=round(dt, 2))
    if err:
        rec["err"] = err; log(rec); return None
    wav = f"{OUT}/{case}.wav"
    try:
        sec = ac.save_audio(r, wav)
    except Exception as e:
        rec["err"] = f"save: {e}; ctype {r[1]}; head {r[0][:200]!r}"; log(rec); return None
    rec.update(wav=wav, seconds=round(sec, 2), rtf=round(dt / max(sec, 0.01), 2)); log(rec); return wav

def speech(model, text, **kw):
    b = {"model": model, "input": text, "seed": SEED}
    b.update({k: v for k, v in kw.items() if v is not None}); return b

group = sys.argv[1]; backend = sys.argv[2] if len(sys.argv) > 2 else "vulkan"
s = ac.Server(backend=backend)
try:
    m = {"backend": backend}
    if group == "irodori":
        m["model"] = "irodori"
        run(s, "irodori_ja_ref_vdes", "/v1/audio/speech", speech("irodori-vdes", JA_REF_TEXT, options={"language": "ja", "no_ref": True,
            "instruction": "落ち着いた若い女性の指揮官。澄んだ声で、丁寧にはっきりと話している。"}), dict(m, lang="ja", text=JA_REF_TEXT, kind="design"))
        os.replace(f"{OUT}/irodori_ja_ref_vdes.wav", JA_REF) if os.path.exists(f"{OUT}/irodori_ja_ref_vdes.wav") else None
        ref = {"type": "path", "path": JA_REF}
        for case, text, emo in (("irodori_ja_J1", J1, "neutral"), ("irodori_ja_J2", J2, "neutral"), ("irodori_ja_J2_angry", "😠" + J2, "angry"),
                                ("irodori_ja_J2_sad", "😭" + J2, "sad"), ("irodori_ja_J2_whisper", "👂" + J2, "whisper"),
                                ("irodori_ja_J3_happy", "😆" + J3, "happy"), ("irodori_ja_J3_giggle", "🤭" + J3, "laugh")):
            run(s, case, "/v1/audio/speech", speech("irodori-clon", text, voice_ref=ref, options={"language": "ja", "no_ref": False}),
                dict(m, lang="ja", text=text, emotion=emo, ref=JA_REF, kind="clone"))
        run(s, "irodori_ja_J1_repeat", "/v1/audio/speech", speech("irodori-clon", J1, voice_ref=ref, options={"language": "ja", "no_ref": False}),
            dict(m, lang="ja", text=J1, emotion="neutral", ref=JA_REF, kind="clone_warm"))
    elif group == "omni":
        m["model"] = "omnivoice"
        ref = {"type": "path", "path": EN_REF}
        for case, text, emo in (("omni_en_E1", E1, "neutral"), ("omni_en_E2", E2, "neutral"), ("omni_en_E2_sigh", "[sigh] " + E2, "sigh"),
                                ("omni_en_E3_laugh", "[laughter] " + E3, "laugh")):
            run(s, case, "/v1/audio/speech", speech("omnivoice", text, voice_ref=ref, reference_text=EN_REF_TEXT, options={"language": "en"}),
                dict(m, lang="en", text=text, emotion=emo, ref=EN_REF, kind="clone"))
        jref = {"type": "path", "path": JA_REF}
        for case, text in (("omni_ja_J1", J1), ("omni_ja_J2", J2)):
            run(s, case, "/v1/audio/speech", speech("omnivoice", text, voice_ref=jref, reference_text=JA_REF_TEXT, options={"language": "ja"}),
                dict(m, lang="ja", text=text, emotion="neutral", ref=JA_REF, kind="clone"))
        run(s, "omni_en_E1_repeat", "/v1/audio/speech", speech("omnivoice", E1, voice_ref=ref, reference_text=EN_REF_TEXT, options={"language": "en"}),
            dict(m, lang="en", text=E1, emotion="neutral", ref=EN_REF, kind="clone_warm"))
    elif group == "auk":
        m["model"] = "auk-flash"
        ref = {"type": "path", "path": EN_REF}
        def zs(t): return f'Say the following with the same voice: "{t}"'
        out = {}
        for case, text in (("auk_en_E1", E1), ("auk_en_E2", E2), ("auk_en_E3", E3)):
            out[case] = run(s, case, "/v1/audio/speech", speech("auk", zs(text), voice_ref=ref, options={"duration_sec": en_dur(text)}),
                            dict(m, lang="en", text=text, emotion="neutral", ref=EN_REF, kind="clone"))
        run(s, "auk_en_E1_repeat", "/v1/audio/speech", speech("auk", zs(E1), voice_ref=ref, options={"duration_sec": en_dur(E1)}),
            dict(m, lang="en", text=E1, emotion="neutral", ref=EN_REF, kind="clone_warm"))
        src = out.get("auk_en_E2")
        if src:
            for case, instr, emo in (("auk_en_E2_angry", "Change the emotion to angry.", "angry"), ("auk_en_E2_sad", "Change the emotion to sad.", "sad"),
                                     ("auk_en_E2_whisper", "Convert this speech into a soft whisper while preserving the speaker and content.", "whisper")):
                run(s, case, "/v1/tasks/run", {"model": "auk-edit", "request": {"text": instr, "audio": src, "seed": SEED}},
                    dict(m, lang="en", text=E2, emotion=emo, ref=EN_REF, kind="edit"))
        src = out.get("auk_en_E3")
        if src:
            run(s, "auk_en_E3_happy", "/v1/tasks/run", {"model": "auk-edit", "request": {"text": "Change the emotion to happy.", "audio": src, "seed": SEED}},
                dict(m, lang="en", text=E3, emotion="happy", ref=EN_REF, kind="edit"))
        if os.path.exists(JA_REF):
            run(s, "auk_ja_J1", "/v1/audio/speech", speech("auk", zs(J1), voice_ref={"type": "path", "path": JA_REF}, options={"duration_sec": ja_dur(J1)}),
                dict(m, lang="ja", text=J1, emotion="neutral", ref=JA_REF, kind="clone"))
finally:
    s.close()
