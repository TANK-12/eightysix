"""
Japanese Tutor — a chat workspace backed by your local Jan model, with a
click-to-type kana keyboard and formal/casual + persona controls. Rebuilt from
jap.py but pointed at Jan (already running) instead of bundling llama-cpp.

Optional: mic capture (SpeechRecognition + PyAudio) and TTS (pyttsx3) if present.
"""

import threading

import customtkinter as ctk

from .. import ui

HIRA = [
    "あ い う え お", "か き く け こ", "さ し す せ そ", "た ち つ て と",
    "な に ぬ ね の", "は ひ ふ へ ほ", "ま み む め も", "や ゆ よ",
    "ら り る れ ろ", "わ を ん",
    "が ぎ ぐ げ ご", "ざ じ ず ぜ ぞ", "だ ぢ づ で ど", "ば び ぶ べ ぼ", "ぱ ぴ ぷ ぺ ぽ",
    "きゃ きゅ きょ", "しゃ しゅ しょ", "ちゃ ちゅ ちょ", "にゃ にゅ にょ",
]
KATA = [
    "ア イ ウ エ オ", "カ キ ク ケ コ", "サ シ ス セ ソ", "タ チ ツ テ ト",
    "ナ ニ ヌ ネ ノ", "ハ ヒ フ ヘ ホ", "マ ミ ム メ モ", "ヤ ユ ヨ",
    "ラ リ ル レ ロ", "ワ ヲ ン", "ー 、 。",
]


class JapaneseTutor:
    NAME = "Japanese Tutor"
    ICON = "🇯🇵"

    def __init__(self, parent, ctx):
        self.ctx = ctx
        self.s = ctx.settings
        self.history = []
        self._build(parent)

    def _build(self, f):
        self.tabs = ctk.CTkTabview(f, fg_color=self.ctx.pal["surface"])
        self.tabs.pack(fill="both", expand=True, padx=14, pady=10)
        self.tabs.add("Chat")
        self.tabs.add("Kana keyboard")
        self.tabs.add("Settings")
        self._chat(self.tabs.tab("Chat"))
        self._kb(self.tabs.tab("Kana keyboard"))
        self._settings(self.tabs.tab("Settings"))

    def _chat(self, f):
        c = ui.card(f, self.ctx, "Workspace")
        up = self.ctx.jan.up() if self.ctx.jan else False
        ui.hint(c, self.ctx, f"Jan {'online' if up else 'OFFLINE — open Jan and start its local API server'}. "
                             "Model is set in Settings.")
        self.view = ctk.CTkTextbox(c, font=self.ctx.f_body, height=360, fg_color=self.ctx.pal["console"])
        self.view.pack(fill="both", expand=True, padx=16, pady=6)
        r = ui.row(c)
        self.entry = ctk.CTkEntry(r, font=("", 15), fg_color=self.ctx.pal["surface_2"])
        self.entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.entry.bind("<Return>", lambda e: self._send())
        ui.button(r, self.ctx, "Send", self._send, primary=True)

    def _kb(self, f):
        c = ui.card(f, self.ctx, "Click a kana — it types into the Chat box")
        wrap = ctk.CTkScrollableFrame(c, fg_color=self.ctx.pal["surface_2"], height=440)
        wrap.pack(fill="both", expand=True, padx=12, pady=8)
        for group in (HIRA + ["—"] + KATA):
            if group == "—":
                ctk.CTkLabel(wrap, text="Katakana", font=self.ctx.f_h2).pack(anchor="w", pady=(10, 2))
                continue
            rr = ctk.CTkFrame(wrap, fg_color="transparent")
            rr.pack(anchor="w", pady=2)
            for ch in group.split():
                ctk.CTkButton(rr, text=ch, width=42, font=("", 16),
                              fg_color=self.ctx.pal["surface"], hover_color=self.ctx.acc["primary"],
                              command=lambda ch=ch: self._type(ch)).pack(side="left", padx=2)

    def _type(self, ch):
        self.entry.insert("insert", ch)
        self.tabs.set("Chat")
        self.entry.focus_set()

    def _settings(self, f):
        c = ui.card(f, self.ctx, "Model & persona")
        models = self.ctx.jan.models() if self.ctx.jan else []
        self.model = ui.opt(c, self.ctx, "Jan model", models or ["(start Jan)"],
                            self.s.get("jan_model") or (models[0] if models else "(start Jan)"), width=320)
        self.register = ui.opt(c, self.ctx, "Register", ["Casual / plain", "Polite (です・ます)", "Formal keigo"],
                               "Polite (です・ます)", width=220)
        self.persona = ui.opt(c, self.ctx, "AI persona",
                              ["Strict translator", "Balanced tutor", "Free conversation partner"],
                              "Balanced tutor", width=240)
        self.romaji = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(ui.row(c), text="include romaji + English breakdown", variable=self.romaji,
                        font=self.ctx.f_small).pack(side="left")
        ui.button(ui.row(c), self.ctx, "Save", self._save_settings, primary=True)

    def _save_settings(self):
        self.s["jan_model"] = self.model.get()
        self.ctx.save_settings()
        self.ctx.log("Japanese Tutor settings saved.")

    def _append(self, who, text):
        self.ctx.ui(lambda: (self.view.insert("end", f"[{who}]  {text}\n\n"), self.view.see("end")))

    def _send(self):
        msg = self.entry.get().strip()
        if not msg:
            return
        self.entry.delete(0, "end")
        self._append("You", msg)
        model = self.model.get()
        reg = self.register.get()
        per = self.persona.get()
        romaji = self.romaji.get()

        def work():
            if not self.ctx.jan or not self.ctx.jan.up():
                self._append("System", "Jan is offline — open Jan and start its local API server.")
                return
            system = (f"You are a Japanese language {per.lower()}. Reply in natural Japanese in a "
                      f"{reg} register. "
                      + ("Then give a line of romaji and a short English gloss." if romaji
                         else "Japanese only."))
            try:
                out = self.ctx.jan.chat(model, system, msg, max_tokens=400, temperature=0.5)
            except Exception as e:
                out = f"(error: {e})"
            self._append("先生", out)
        threading.Thread(target=work, daemon=True).start()
