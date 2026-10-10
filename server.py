#!/usr/bin/env python3
# Prototype only. Uses public profile pages; unofficial and may stop working.
import json, re, time, os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LAST_REQUEST = 0.0

def find_nested(obj, wanted):
    if isinstance(obj, dict):
        if wanted in obj:
            yield obj[wanted]
        for value in obj.values():
            yield from find_nested(value, wanted)
    elif isinstance(obj, list):
        for value in obj:
            yield from find_nested(value, wanted)

def check_username(username):
    global LAST_REQUEST
    # Keep requests slow and sequential; do not use proxies or retry around blocks.
    wait = 2.0 - (time.time() - LAST_REQUEST)
    if wait > 0:
        time.sleep(wait)
    url = "https://www.tiktok.com/@" + username
    req = Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.8"
    })
    LAST_REQUEST = time.time()
    try:
        with urlopen(req, timeout=12) as resp:
            page = resp.read(3_000_000).decode("utf-8", "replace")
    except (HTTPError, URLError, TimeoutError, OSError):
        return "unknown"

    match = re.search(
        r"<script[^>]+id=[\"\']__UNIVERSAL_DATA_FOR_REHYDRATION__[\"\'][^>]*>(.*?)</script>",
        page, re.S
    )
    if not match:
        return "unknown"
    try:
        data = json.loads(match.group(1))
    except (json.JSONDecodeError, TypeError):
        return "unknown"

    # A populated user-detail object is evidence that a profile exists.
    for value in find_nested(data, "user-detail"):
        if isinstance(value, dict):
            info = value.get("userInfo")
            if isinstance(info, dict) and isinstance(info.get("user"), dict):
                user = info.get("user") or {}
                if user.get("uniqueId"):
                    return "taken"

    # Only classify as likely available when TikTok explicitly returns a known
    # user-not-found status. Missing profile data alone is NOT enough.
    for value in find_nested(data, "statusCode"):
        if value in (10202, 10221, "10202", "10221"):
            return "likely_available"
    return "unknown"

class Handler(BaseHTTPRequestHandler):
    def _send(self, status, body, content_type="application/json; charset=utf-8"):
        raw = body if isinstance(body, bytes) else body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            self._send(200, (ROOT / "index.html").read_bytes(), "text/html; charset=utf-8")
        else:
            self._send(404, json.dumps({"error":"not found"}))

    def do_POST(self):
        if self.path != "/api/check":
            self._send(404, json.dumps({"error":"not found"})); return
        try:
            length = min(int(self.headers.get("Content-Length", "0")), 10000)
            payload = json.loads(self.rfile.read(length))
            username = str(payload.get("username", "")).lstrip("@")
            if not re.fullmatch(r"[A-Za-z0-9._]{2,24}", username):
                self._send(400, json.dumps({"error":"invalid username"})); return
            status = check_username(username)
            self._send(200, json.dumps({"username":username,"status":status}))
        except Exception:
            self._send(500, json.dumps({"status":"unknown"}))

    def log_message(self, fmt, *args):
        print("%s - %s" % (self.address_string(), fmt % args))

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    print(f"Server listening on port {port}.")
    print("Unofficial profile-page check; TikTok may block or change its page format.")
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()
