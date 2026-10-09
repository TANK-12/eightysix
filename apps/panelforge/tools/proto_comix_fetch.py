"""Prototype: fetch one comix.to chapter losslessly via headless Chrome (CDP)."""

import base64, json, subprocess, sys, time, urllib.request, os
import websocket

CHAPTER_URL, OUT = sys.argv[1], sys.argv[2]
PORT = 9334
os.makedirs(OUT, exist_ok=True)
proc = subprocess.Popen(
    [
        "flatpak",
        "run",
        "com.google.Chrome",
        "--headless=new",
        "--disable-gpu",
        f"--remote-debugging-port={PORT}",
        "--remote-allow-origins=*",
        "--user-data-dir=" + os.path.expanduser("~/.var/app/com.google.Chrome/pf-cdp"),
        "--window-size=1000,1400",
        "about:blank",
    ],
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
)
for _ in range(60):
    try:
        tabs = json.load(urllib.request.urlopen(f"http://localhost:{PORT}/json"))
        break
    except Exception:
        time.sleep(0.5)
page = [t for t in tabs if t["type"] == "page"][0]
ws = websocket.create_connection(
    page["webSocketDebuggerUrl"], timeout=120, suppress_origin=True
)
n = 0


def call(method, **params):
    global n
    n += 1
    ws.send(json.dumps({"id": n, "method": method, "params": params}))
    while True:
        m = json.loads(ws.recv())
        if m.get("id") == n:
            return m.get("result", {})


def ev(js, await_promise=False):
    r = call(
        "Runtime.evaluate",
        expression=js,
        returnByValue=True,
        awaitPromise=await_promise,
    )
    return r.get("result", {}).get("value")


try:
    call("Page.enable")
    call(
        "Emulation.setDeviceMetricsOverride",
        width=1000,
        height=1400,
        deviceScaleFactor=1,
        mobile=False,
    )
    call("Page.navigate", url=CHAPTER_URL)
    time.sleep(8)
    ev(
        "(()=>{const st=document.createElement('style');st.textContent='body *{visibility:hidden !important} canvas.rpage-page__img, img.rpage-page__img{visibility:visible !important}';document.head.appendChild(st)})()"
    )
    total = ev("document.querySelectorAll('.rpage-page').length")
    print("page slots:", total)
    UA = ev("navigator.userAgent")
    pages = {}
    only = (
        [int(x) for x in sys.argv[3].split(",")]
        if len(sys.argv) > 3
        else range(1, total + 1)
    )
    for idx in only:
        got = None
        for attempt in range(2):  # two passes per page
            ev(
                f"document.querySelector('.rpage-page[data-page=\"{idx}\"]').scrollIntoView({{block:'center'}})"
            )
            for _ in range(40):
                info = ev(
                    f"""(()=>{{const p=document.querySelector('.rpage-page[data-page="{idx}"]');
                  const c=p&&p.querySelector('canvas.rpage-page__img'); const i=p&&p.querySelector('img.rpage-page__img');
                  if(c&&c.width>0&&!p.classList.contains('is-loading')){{const r=c.getBoundingClientRect();return {{kind:'canvas',x:r.left+scrollX,y:r.top+scrollY,w:r.width,h:r.height,cw:c.width,ch:c.height}};}}
                  if(i&&i.complete&&i.naturalWidth>0) return {{kind:'img',src:i.currentSrc||i.src}};
                  return null}})()"""
                )
                if info:
                    break
                time.sleep(0.25)
            if not info:
                continue
            if info["kind"] == "canvas":
                from PIL import Image, ImageStat
                import io

                data = None
                prev = None
                for _try in range(20):
                    time.sleep(2.0)
                    ev(
                        f"document.querySelector('.rpage-page[data-page=\"{idx}\"]').scrollIntoView({{block:'start'}})"
                    )
                    r = ev(
                        f"(()=>{{const c=document.querySelector('.rpage-page[data-page=\"{idx}\"] canvas');if(!c)return null;const b=c.getBoundingClientRect();return {{x:b.left+scrollX,y:b.top+scrollY,w:b.width,h:b.height,cw:c.width}}}})()"
                    )
                    if not r:
                        continue
                    shot = call(
                        "Page.captureScreenshot",
                        format="png",
                        clip={
                            "x": r["x"],
                            "y": r["y"],
                            "width": r["w"],
                            "height": r["h"],
                            "scale": r["cw"] / r["w"],
                        },
                    )
                    raw = base64.b64decode(shot["data"])
                    st = ImageStat.Stat(Image.open(io.BytesIO(raw)).convert("L"))
                    if st.stddev[0] > 4 and prev == raw:
                        data = raw
                        break
                    prev = raw
                if data is None:
                    continue
                ext = "png"
            else:
                req = urllib.request.Request(
                    info["src"],
                    headers={"User-Agent": UA, "Referer": "https://comix.to/"},
                )
                try:
                    data = urllib.request.urlopen(req, timeout=30).read()
                except Exception as e:
                    print(idx, "fetch fail", e)
                    continue
                ext = (
                    "webp"
                    if data[8:12] == b"WEBP"
                    else ("png" if data[:4] == b"\x89PNG" else "jpg")
                )
            got = (info["kind"], data, ext)
            break
        if not got:
            print(idx, "MISSING")
            continue
        with open(os.path.join(OUT, f"{idx:03d}.{got[2]}"), "wb") as f:
            f.write(got[1])
        pages[idx] = got[0]
    print(
        "saved",
        len(pages),
        "of",
        total,
        "canvas pages:",
        [k for k, v in pages.items() if v == "canvas"],
    )
finally:
    try:
        call("Browser.close")
    except Exception:
        pass
    proc.wait(timeout=20)
