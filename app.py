#!/usr/bin/env python3
"""Password Vault Keeper: password checker + generator (Python Flask, HTTPS)

Run:  python app.py              -> https://localhost:8443  (this computer only, opens the browser)
      python app.py --lan        -> also reachable from other devices on the same Wi-Fi
      python app.py --port 9000  -> use another port
      python app.py --no-browser -> do not open the browser automatically
"""
import argparse
import datetime
import ipaddress
import math
import re
import secrets
import socket
import sys
import threading
import time
import webbrowser
from collections import defaultdict, deque
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory
from zxcvbn import zxcvbn

BASE = Path(__file__).resolve().parent
STATIC = BASE / "static"

YEAR = 31_557_600          # 365.25 days in seconds
FAST = 1e11                # leaked DB + fast hash + GPU: 100 billion guesses per second (see README)
SAMPLE = "qwer1234"
MAX_LEN = 128

# Common Korean words: typed on an English (QWERTY) keyboard, and in Korean letters
KO_WORDS = [
    "dkssud", "dkssudgktpdy", "tkfkd", "tkfkdgo", "tkfkdgody", "qlalfqjsgh", "qlqjs", "gksrmf",
    "eogksalsrnr", "dnflskfk", "godqhr", "ghkdlxld", "djaak", "rkwhr", "clsrn",
    "안녕하세요", "안녕", "사랑해요", "사랑해", "사랑", "비밀번호", "비번", "대한민국", "우리나라",
    "행복", "화이팅", "가족", "친구",
]

SCENARIOS = [
    ("Guessing at a login page", "Site limits the number of tries", "100 per hour", 100 / 3600),
    ("Guessing at a login page", "Site with no limit", "10 per second", 10.0),
    ("Leaked database, offline attack", "Stored with a slow hash (bcrypt)", "10,000 per second", 1e4),
    ("Leaked database, offline attack", "Stored with a fast hash (MD5, SHA-1)", "100 billion per second", FAST),
]

HANGUL = "가-힣ㄱ-ㅎㅏ-ㅣ"


# ---------------------------------------------------------------- checking
def cardinality(pw: str) -> int:
    """How many different characters an attacker must try for each position."""
    c = 0
    if re.search(r"[a-z]", pw):
        c += 26
    if re.search(r"[A-Z]", pw):
        c += 26
    if re.search(r"[0-9]", pw):
        c += 10
    if re.search(f"[{HANGUL}]", pw):
        c += 2350
    if re.search(f"[^A-Za-z0-9{HANGUL}]", pw):
        c += 33
    return c or 10


def explain(m: dict):
    extra = ""
    if m.get("l33t"):
        extra += " · attackers also try swaps such as a→@ by default"
    if m.get("reversed"):
        extra += " · writing it backwards does not help"
    pattern, token = m["pattern"], m["token"]
    if pattern == "dictionary":
        name = m.get("dictionary_name", "")
        if name == "passwords":
            return f"Common in leaked password lists (rank {m.get('rank')}){extra}", token
        if name == "user_inputs":
            return f"Common Korean word (in Korean letters or typed on an English keyboard){extra}", token
        if "names" in name:
            return f"Common name{extra}", token
        return f"Dictionary word{extra}", token
    return {
        "spatial": ("Keys next to each other on the keyboard", token),
        "repeat": ("Repeated characters or groups", token),
        "sequence": ("Characters or numbers in sequence", token),
        "regex": ("Looks like a year", token),
        "date": ("Looks like a date", token),
    }.get(pattern)


def analyze(pw: str):
    """Return (estimated number of guesses, list of reasons)."""
    card = cardinality(pw)
    head, tail = pw[:72], pw[72:]          # zxcvbn accepts at most 72 characters
    result = zxcvbn(head, user_inputs=KO_WORDS)

    # zxcvbn counts a random character as only 10 possibilities,
    # so recalculate those parts with the real number of character types.
    product, reasons = 1, []
    for m in result["sequence"]:
        if m["pattern"] == "bruteforce":
            product *= card ** len(m["token"])
        else:
            product *= max(1, int(m["guesses"]))
        why = explain(m)
        if why:
            reasons.append({"text": why[0], "token": why[1]})
    guesses = max(int(result["guesses"]), product * math.factorial(len(result["sequence"])))
    guesses *= card ** len(tail)

    if len(pw) < 12:
        reasons.append({"text": f"Only {len(pw)} characters long. 12 or more is recommended", "token": None})
    if not reasons:
        reasons.append({"text": "No known word or pattern was found", "token": None})
    return guesses, reasons


# ---------------------------------------------------------------- showing time
def seconds(guesses: int, rate: float) -> float:
    try:
        return float(guesses) / rate
    except OverflowError:
        return math.inf


def big_years(y: float) -> str:
    if math.isinf(y) or y >= 1e24:
        return "Trillions of times the age of the universe"
    for unit, name in ((1e21, "sextillion"), (1e18, "quintillion"), (1e15, "quadrillion"),
                       (1e12, "trillion"), (1e9, "billion"), (1e6, "million"), (1e3, "thousand")):
        if y >= unit:
            v = y / unit
            num = f"{v:.1f}".rstrip("0").rstrip(".") if v < 100 else f"{round(v):,}"
            return f"About {num} {name} years"
    return f"{round(y):,} years"


def split(s: float):
    y, s = divmod(s, YEAR)
    d, s = divmod(s, 86400)
    h, s = divmod(s, 3600)
    m, s = divmod(s, 60)
    return [int(y), int(d), int(h), int(m), int(s)]


UNITS = ["year", "day", "hour", "minute", "second"]
CLOCK_UNITS = ["years", "days", "hours", "min", "sec"]


def is_huge(s: float) -> bool:
    return math.isinf(s) or s / YEAR >= 10000


def plural(n: int, unit: str) -> str:
    return f"{n:,} {unit}" + ("" if n == 1 else "s")


def time_text(s: float) -> str:
    if s < 1:
        return "Under 1 second"
    if is_huge(s):
        return big_years(s / YEAR)
    parts = split(s)
    i = next(k for k, v in enumerate(parts) if v > 0)
    out = [plural(parts[i], UNITS[i])]
    if i + 1 < 5 and parts[i + 1] > 0:
        out.append(plural(parts[i + 1], UNITS[i + 1]))
    return " ".join(out)


def clock(s: float) -> dict:
    if s < 1:
        return {"single": "Less than 1 second"}
    if is_huge(s):
        return {"single": big_years(s / YEAR)}
    cells, leading = [], True
    for i, v in enumerate(split(s)):
        if v > 0:
            leading = False
        cells.append({"value": f"{v:02d}" if i >= 2 else str(v), "unit": CLOCK_UNITS[i], "zero": leading})
    return {"cells": cells}


def verdict(s: float):
    if s < 60:
        return "crit", "Cracked instantly"
    if s < 86400:
        return "crit", "Very weak"
    if s < YEAR:
        return "warn", "Weak"
    if s < YEAR * 100:
        return "warn", "Fair"
    return "ok", "Strong"


# ---------------------------------------------------------------- generating
SETS = {
    "lower": "abcdefghijklmnopqrstuvwxyz",
    "upper": "ABCDEFGHIJKLMNOPQRSTUVWXYZ",
    "digit": "0123456789",
    "symbol": "!@#$%^&*()-_=+[]{};:,.?/~",
}
AMBIGUOUS = set("0OoIl1|")


def generate(length: int, kinds: list, no_ambiguous: bool):
    """Make a password with the secrets module (cryptographic randomness from the OS)."""
    groups = []
    for kind in ("lower", "upper", "digit", "symbol"):
        if kind in kinds:
            chars = SETS[kind]
            if no_ambiguous:
                chars = "".join(ch for ch in chars if ch not in AMBIGUOUS)
            groups.append(chars)
    if not groups:
        groups = [SETS["lower"]]
    pool = "".join(groups)
    while True:
        pw = "".join(secrets.choice(pool) for _ in range(length))
        if all(any(ch in g for ch in pw) for g in groups):   # until every chosen type appears
            return pw, len(pool)


# ---------------------------------------------------------------- web server
app = Flask(__name__, static_folder=None)
app.config["MAX_CONTENT_LENGTH"] = 4096

# A simple rate limit in case the site is made public: 150 requests per 10 seconds per person
_hits = defaultdict(deque)


@app.before_request
def rate_limit():
    if not request.path.startswith("/api/"):
        return None
    who = request.headers.get("CF-Connecting-IP") or request.remote_addr or "?"
    now = time.monotonic()
    if len(_hits) > 5000:
        _hits.clear()
    q = _hits[who]
    while q and now - q[0] > 10:
        q.popleft()
    if len(q) >= 150:
        return jsonify(error="Too many requests. Try again in a moment."), 429
    q.append(now)
    return None


@app.after_request
def harden(resp):
    resp.headers["Cache-Control"] = "no-store"
    resp.headers["Content-Security-Policy"] = "default-src 'self'; frame-ancestors 'none'"
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["Referrer-Policy"] = "no-referrer"
    return resp


@app.get("/")
def index():
    return send_from_directory(STATIC, "index.html")


@app.get("/static/<path:name>")
def static_file(name):
    return send_from_directory(STATIC, name)


@app.post("/api/check")
def api_check():
    data = request.get_json(silent=True) or {}
    typed = data.get("password")
    typed = typed[:MAX_LEN] if isinstance(typed, str) else ""
    pw = typed or SAMPLE                     # show an example when nothing is typed
    guesses, reasons = analyze(pw)
    fast = seconds(guesses, FAST)
    level, label = verdict(fast)
    return jsonify(
        sample=None if typed else SAMPLE,
        level=level,
        label=label,
        clock=clock(fast),
        meter=max(3, min(100, round(math.log10(max(guesses, 1)) / 24 * 100))),
        reasons=reasons,
        scenarios=[
            {"name": n, "note": note, "speed": speed, "time": time_text(seconds(guesses, rate))}
            for n, note, speed, rate in SCENARIOS
        ],
    )


@app.post("/api/generate")
def api_generate():
    data = request.get_json(silent=True) or {}
    try:
        length = int(data.get("length", 20))
    except (TypeError, ValueError):
        length = 20
    length = max(8, min(64, length))
    kinds = data.get("kinds") if isinstance(data.get("kinds"), list) else list(SETS)
    pw, pool = generate(length, kinds, bool(data.get("no_ambiguous", True)))
    return jsonify(
        password=pw,
        length=length,
        pool=pool,
        bits=round(length * math.log2(pool)),
        time=time_text(seconds(pool ** length, FAST)),
    )


# ---------------------------------------------------------------- HTTPS certificate
def lan_ip():
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))      # no packet is actually sent
            return s.getsockname()[0]
    except OSError:
        return None


def ensure_cert():
    """Create a self-signed certificate on the first run and keep it in certs/."""
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID

    folder = BASE / "certs"
    cert_path, key_path = folder / "cert.pem", folder / "key.pem"
    if cert_path.exists() and key_path.exists():
        return str(cert_path), str(key_path)

    folder.mkdir(exist_ok=True)
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")])
    alt = [x509.DNSName("localhost"), x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]
    ip = lan_ip()
    if ip and ip != "127.0.0.1":
        alt.append(x509.IPAddress(ipaddress.ip_address(ip)))
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(days=1))
        .not_valid_after(now + datetime.timedelta(days=825))
        .add_extension(x509.SubjectAlternativeName(alt), critical=False)
        .sign(key, hashes.SHA256())
    )
    key_path.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    try:
        key_path.chmod(0o600)
    except OSError:
        pass
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    return str(cert_path), str(key_path)


def main():
    parser = argparse.ArgumentParser(description="Password Vault Keeper HTTPS server")
    parser.add_argument("--port", type=int, default=8443)
    parser.add_argument("--lan", action="store_true", help="allow other devices on the same network to connect")
    parser.add_argument("--no-browser", action="store_true", help="do not open the browser automatically")
    args = parser.parse_args()

    if not args.no_browser:
        threading.Timer(1.5, webbrowser.open, [f"https://localhost:{args.port}"]).start()

    host = "0.0.0.0" if args.lan else "127.0.0.1"
    print(f"\n  Password Vault Keeper  ->  https://localhost:{args.port}")
    if args.lan and lan_ip():
        print(f"  From other devices     ->  https://{lan_ip()}:{args.port}")
    print("  (The certificate is self-signed, so the browser warns the first time."
          " Choose 'Advanced > Proceed'.)\n")
    app.run(host=host, port=args.port, ssl_context=ensure_cert())


if __name__ == "__main__":
    main()
