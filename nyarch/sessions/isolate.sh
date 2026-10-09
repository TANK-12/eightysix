#!/bin/bash
B=$HOME/.var/app/ai.jan.Jan/data/Jan/data/llamacpp/backends/b9967/linux-vulkan-x64/build/bin
D=$HOME/.var/app/ai.jan.Jan/data/Jan/data/llamacpp/models/Qwen3_5-4B-IQ4_XS
export LD_LIBRARY_PATH="$B:$LD_LIBRARY_PATH"
PORT=39007
try() {
  local label="$1"; shift
  "$B/llama-server" --model "$D/model.gguf" --host 127.0.0.1 --port $PORT \
    --no-webui --ctx-size 8192 --fit off "$@" > /tmp/iso.log 2>&1 &
  local pid=$!
  for i in $(seq 1 150); do curl -s -m 2 http://127.0.0.1:$PORT/health 2>/dev/null | grep -q '"ok"' && break; sleep 2; done
  python3 - "$PORT" "$label" <<'PY'
import json, os, sys, time, urllib.request
S=os.path.expanduser("~/Forge/nyarch/sessions")
text=open(f"{S}/article-sample.txt").read()
body={"messages":[{"role":"user","content":"Explain this article in 3 sentences.\n\n"+text}],
      "max_tokens":160,"temperature":0.2,"chat_template_kwargs":{"enable_thinking":False}}
r=urllib.request.Request(f"http://127.0.0.1:{sys.argv[1]}/v1/chat/completions",
    data=json.dumps(body).encode(),headers={"Content-Type":"application/json"})
t=time.time()
try:
    with urllib.request.urlopen(r,timeout=900) as resp: d=json.load(resp)
    out=d["choices"][0]["message"]["content"].strip()
    bad=[c for c in out if 0x0600<=ord(c)<=0x06FF or 0x3000<=ord(c)<=0x9FFF]
    print(f"### {sys.argv[2]}")
    print(f"    {time.time()-t:.0f}s | garbage chars: {len(bad)} {bad[:8] if bad else '(CLEAN)'}")
    print(f"    {out[:150]}")
except Exception as e: print(f"### {sys.argv[2]}\n    FAILED {e}")
PY
  kill $pid 2>/dev/null; wait $pid 2>/dev/null; sleep 4
}
try "iGPU 40 layers, flash-attn on, q8_0 KV  (current Jan setup)" --n-gpu-layers 40 --threads 4 --flash-attn on --cache-type-k q8_0 --cache-type-v q8_0
try "iGPU 40 layers, flash-attn on, f16 KV"                       --n-gpu-layers 40 --threads 4 --flash-attn on
try "CPU only, f16 KV"                                            --n-gpu-layers 0  --threads 10
echo ISO_DONE
