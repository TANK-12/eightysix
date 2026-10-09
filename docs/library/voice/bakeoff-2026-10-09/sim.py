"""Speaker similarity (cosine of wespeaker ResNet34 embeddings) of each wav to a reference.
usage: sim.py ref.wav a.wav b.wav ...  -> JSON {path: cosine}"""
import json, sys, wave
import numpy as np
import sherpa_onnx
cfg = sherpa_onnx.SpeakerEmbeddingExtractorConfig(model="/tmp/v120/wespeaker_en_voxceleb_resnet34_LM.onnx", num_threads=2)
ex = sherpa_onnx.SpeakerEmbeddingExtractor(cfg)
def emb(path):
    with wave.open(path) as w:
        rate, n, ch, sw = w.getframerate(), w.getnframes(), w.getnchannels(), w.getsampwidth()
        x = np.frombuffer(w.readframes(n), dtype="<i2" if sw == 2 else "<i4").astype(np.float32)
        x = x.reshape(-1, ch).mean(1) / (32768.0 if sw == 2 else 2147483648.0)
    s = ex.create_stream(); s.accept_waveform(rate, x); s.input_finished()
    e = np.array(ex.compute(s)); return e / np.linalg.norm(e)
r = emb(sys.argv[1])
print(json.dumps({p: round(float(np.dot(r, emb(p))), 3) for p in sys.argv[2:]}))
