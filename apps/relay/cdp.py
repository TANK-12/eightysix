"""A tiny Chrome DevTools Protocol client, stdlib only.

Qt WebEngine (Whatsie) and Chrome open a local DevTools port when asked; this
talks to one page on it: run JavaScript, type text, press keys. Just enough
websocket (RFC 6455) for that: masked client frames, text and continuation
frames, ping/pong, and lengths up to 64 bits.
"""

from __future__ import annotations

import base64
import json
import os
import socket
import struct
import time
import urllib.parse
import urllib.request

TIMEOUT = 15


def pages(port: int, host: str = "127.0.0.1") -> list[dict]:
    with urllib.request.urlopen(f"http://{host}:{port}/json/list", timeout=3) as r:
        return json.loads(r.read().decode())


def find_page(port: int, url_part: str, host: str = "127.0.0.1") -> dict | None:
    return next(
        (
            p
            for p in pages(port, host)
            if p.get("type") == "page" and url_part in p.get("url", "")
        ),
        None,
    )


def frame(payload: bytes, opcode: int = 1, mask: bytes | None = None) -> bytes:
    """One masked client frame."""
    mask = mask if mask is not None else os.urandom(4)
    head = bytes([0x80 | opcode])
    size = len(payload)
    if size < 126:
        head += bytes([0x80 | size])
    elif size < 65536:
        head += bytes([0x80 | 126]) + struct.pack(">H", size)
    else:
        head += bytes([0x80 | 127]) + struct.pack(">Q", size)
    masked = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
    return head + mask + masked


class Page:
    """One open DevTools websocket to a page."""

    def __init__(self, ws_url: str, timeout: float = TIMEOUT) -> None:
        url = urllib.parse.urlparse(ws_url)
        self.sock = socket.create_connection(
            (url.hostname, url.port or 80), timeout=timeout
        )
        key = base64.b64encode(os.urandom(16)).decode()
        self.sock.sendall(
            (
                f"GET {url.path} HTTP/1.1\r\nHost: {url.netloc}\r\n"
                "Upgrade: websocket\r\nConnection: Upgrade\r\n"
                f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n"
            ).encode()
        )
        reply = b""
        while b"\r\n\r\n" not in reply:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise ConnectionError("DevTools closed the handshake")
            reply += chunk
        head, _, self.buffer = reply.partition(b"\r\n\r\n")
        if b" 101 " not in head.split(b"\r\n", 1)[0]:
            raise ConnectionError(head.split(b"\r\n", 1)[0].decode(errors="replace"))
        self.next_id = 0
        self.timeout = timeout
        self.events: list[dict] = []  # events that came while waiting for replies

    def close(self) -> None:
        try:
            self.sock.sendall(frame(b"", opcode=8))
        except OSError:
            pass
        self.sock.close()

    def __enter__(self) -> "Page":
        return self

    def __exit__(self, *_) -> None:
        self.close()

    def _read(self, size: int) -> bytes:
        while len(self.buffer) < size:
            chunk = self.sock.recv(65536)
            if not chunk:
                raise ConnectionError("DevTools closed the connection")
            self.buffer += chunk
        data, self.buffer = self.buffer[:size], self.buffer[size:]
        return data

    def _message(self) -> str:
        parts: list[bytes] = []
        while True:
            b1, b2 = self._read(2)
            opcode, size = b1 & 0x0F, b2 & 0x7F
            if size == 126:
                size = struct.unpack(">H", self._read(2))[0]
            elif size == 127:
                size = struct.unpack(">Q", self._read(8))[0]
            mask = self._read(4) if b2 & 0x80 else b""
            data = self._read(size)
            if mask:
                data = bytes(b ^ mask[i % 4] for i, b in enumerate(data))
            if opcode == 8:
                raise ConnectionError("DevTools closed the connection")
            if opcode == 9:
                self.sock.sendall(frame(data, opcode=10))
                continue
            if opcode in (0, 1, 2):
                parts.append(data)
                if b1 & 0x80:
                    return b"".join(parts).decode()

    def call(self, method: str, **params) -> dict:
        self.next_id += 1
        wanted = self.next_id
        body = json.dumps({"id": wanted, "method": method, "params": params})
        self.sock.sendall(frame(body.encode()))
        while True:
            reply = json.loads(self._message())
            if "method" in reply:
                self.events = (self.events + [reply])[-200:]
            if reply.get("id") == wanted:
                if "error" in reply:
                    raise RuntimeError(f"{method}: {reply['error'].get('message')}")
                return reply.get("result") or {}

    def wait_event(self, method: str, seconds: float = 5) -> dict | None:
        """The params of the next `method` event (one already buffered
        counts), or None after `seconds`."""
        end = time.time() + seconds
        while True:
            for i, event in enumerate(self.events):
                if event.get("method") == method:
                    del self.events[i]
                    return event.get("params") or {}
            left = end - time.time()
            if left <= 0:
                return None
            self.sock.settimeout(left)
            try:
                message = json.loads(self._message())
            except (TimeoutError, socket.timeout):
                return None
            finally:
                self.sock.settimeout(self.timeout)
            if "method" in message:
                self.events.append(message)

    def js(self, expression: str):
        """Run JavaScript in the page; the value comes back as JSON data."""
        result = self.call(
            "Runtime.evaluate",
            expression=expression,
            returnByValue=True,
            awaitPromise=True,
        )
        if "exceptionDetails" in result:
            detail = result["exceptionDetails"]
            text = (detail.get("exception") or {}).get("description") or detail.get(
                "text"
            )
            raise RuntimeError(f"page script failed: {text}")
        return (result.get("result") or {}).get("value")

    def type_text(self, text: str) -> None:
        self.call("Input.insertText", text=text)

    def key(self, name: str, code: int, modifiers: int = 0) -> None:
        for kind in ("rawKeyDown", "keyUp"):
            self.call(
                "Input.dispatchKeyEvent",
                type=kind,
                key=name,
                code=name,
                windowsVirtualKeyCode=code,
                nativeVirtualKeyCode=code,
                modifiers=modifiers,
            )

    def screenshot(self, path: str) -> None:
        data = self.call("Page.captureScreenshot", format="png").get("data", "")
        with open(path, "wb") as f:
            f.write(base64.b64decode(data))


def open_page(port: int, url_part: str, timeout: float = TIMEOUT) -> Page:
    found = find_page(port, url_part)
    if not found:
        raise ConnectionError(f"no page with {url_part} on port {port}")
    return Page(found["webSocketDebuggerUrl"], timeout=timeout)
