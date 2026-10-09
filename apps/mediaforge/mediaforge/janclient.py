"""
Minimal OpenAI-compatible client for a local Jan / llama.cpp server.
Used for subtitle translation and the Japanese tutor chat.
"""

import json
import requests


class JanClient:
    def __init__(self, base_url, timeout=900):
        self.base = base_url.rstrip("/")
        self.timeout = timeout
        self.s = requests.Session()

    def up(self):
        try:
            return self.s.get(f"{self.base}/models", timeout=5).status_code == 200
        except Exception:
            return False

    def models(self):
        try:
            r = self.s.get(f"{self.base}/models", timeout=8)
            r.raise_for_status()
            return [m["id"] for m in r.json().get("data", []) if m.get("id")]
        except Exception:
            return []

    def chat(self, model, system, user, max_tokens=1024, temperature=0.3, stream=False, on_delta=None):
        payload = {
            "model": model,
            "messages": ([{"role": "system", "content": system}] if system else [])
            + [{"role": "user", "content": user}],
            "temperature": temperature, "max_tokens": max_tokens,
            "chat_template_kwargs": {"enable_thinking": False, "thinking": False},
        }
        if not stream:
            r = self.s.post(f"{self.base}/chat/completions", json=payload, timeout=self.timeout)
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"].strip()

        payload["stream"] = True
        r = self.s.post(f"{self.base}/chat/completions", json=payload, stream=True, timeout=self.timeout)
        r.raise_for_status()
        buf = b""
        parts = []
        for chunk in r.iter_content(chunk_size=2048):
            buf += chunk
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                line = line.decode("utf-8", "replace").strip()
                if not line.startswith("data:"):
                    continue
                line = line[5:].strip()
                if line == "[DONE]":
                    return "".join(parts).strip()
                try:
                    d = json.loads(line)
                    piece = d["choices"][0]["delta"].get("content") or ""
                except Exception:
                    piece = ""
                if piece:
                    parts.append(piece)
                    if on_delta:
                        on_delta(piece)
        return "".join(parts).strip()
