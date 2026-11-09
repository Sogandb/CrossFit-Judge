#!/usr/bin/env python3
"""End-to-end smoke test through the PUBLIC web address (no extra packages).

    python3 deploy/smoke_test.py http://SERVER:8080 [user:password] [video.mp4]

Uploads a video with the real chunked-upload protocol, waits for the analysis
and prints the overview. Without a video argument it generates a 20 s
test clip with ffmpeg (no athlete in it -> the expected result is a clean
"0 valid reps" completion, which proves upload + validation + pose engine +
alignment + review-video rendering all work on THIS server).
"""
import base64, json, os, subprocess, sys, tempfile, time, urllib.request, uuid

base = sys.argv[1].rstrip("/")
auth = sys.argv[2] if len(sys.argv) > 2 and ":" in sys.argv[2] else None
video = next((a for a in sys.argv[2:] if a.endswith((".mp4", ".mov", ".webm"))), None)
API = base + "/api/judge"


def req(method, url, data=None, headers=None, timeout=120):
    h = dict(headers or {})
    if auth:
        h["Authorization"] = "Basic " + base64.b64encode(auth.encode()).decode()
    r = urllib.request.Request(url, data=data, headers=h, method=method)
    with urllib.request.urlopen(r, timeout=timeout) as resp:
        return resp.status, resp.read()


def form(fields, files=None):
    b = uuid.uuid4().hex
    out = b""
    for k, v in fields.items():
        out += f'--{b}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode()
    for k, (fn, blob) in (files or {}).items():
        out += (f'--{b}\r\nContent-Disposition: form-data; name="{k}"; filename="{fn}"\r\n'
                f'Content-Type: application/octet-stream\r\n\r\n').encode() + blob + b"\r\n"
    out += f"--{b}--\r\n".encode()
    return out, {"Content-Type": f"multipart/form-data; boundary={b}"}


def step(msg):
    print(f"[smoke] {msg}", flush=True)


# 1) web + engine health
step("web health");    print("   ", req("GET", base + "/healthz")[1].decode())
for _ in range(60):    # engine may still be warming up
    try:
        h = json.loads(req("GET", API + "/health")[1]); break
    except Exception as e:
        time.sleep(3)
else:
    sys.exit("engine did not become healthy")
step(f"engine health: deps_ok={h.get('deps_ok')} ffmpeg={h.get('ffmpeg_ok')} model={h.get('model_present')}")
assert h.get("deps_ok") and h.get("ffmpeg_ok") and h.get("model_present"), h

# 2) video
if not video:
    video = os.path.join(tempfile.mkdtemp(), "smoke.mp4")
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
                    "testsrc=s=854x480:d=20:r=30", "-c:v", "libx264", "-preset", "ultrafast",
                    "-pix_fmt", "yuv420p", video], check=True)
data = open(video, "rb").read()
step(f"video {len(data)/1e6:.1f} MB")

# 3) chunked upload
body, hd = form({"filename": os.path.basename(video), "total_bytes": str(len(data)),
                 "division": "m_18_34_rx", "wod_id": "wodx_ladder_wod1", "athlete_name": "smoke"})
jid = json.loads(req("POST", API + "/jobs/init", body, hd)[1])["job_id"]
step(f"job {jid}")
CH = 1 << 20
for off in range(0, len(data), CH):
    body, hd = form({"offset": str(off)}, {"blob": ("c", data[off:off + CH])})
    req("POST", f"{API}/jobs/{jid}/chunk", body, hd)
body, hd = form({})
req("POST", f"{API}/jobs/{jid}/complete", body, hd)
step("upload complete — analysing")
t0 = time.time()
while True:
    j = json.loads(req("GET", f"{API}/jobs/{jid}")[1])["job"]
    if j["status"] in ("done", "failed"):
        break
    if time.time() - t0 > 900:
        sys.exit("timeout")
    time.sleep(2)
assert j["status"] == "done", j.get("error_en")
res = json.loads(req("GET", f"{API}/jobs/{jid}/result")[1])
res = res.get("result", res)
step(f"DONE in {time.time()-t0:.0f}s: {res['overview']['line_en']}")
time.sleep(5)  # review video renders asynchronously
code, _ = req("GET", f"{API}/jobs/{jid}/video?variant=review", headers={"Range": "bytes=0-99"})
step(f"review video HTTP {code}")
print("[smoke] PASS")
