#!/usr/bin/env python3
"""비밀번호 금고지기: 비밀번호 진단 + 생성 (파이썬 Flask, HTTPS)

실행:  python app.py              -> https://localhost:8443  (이 컴퓨터에서만 접속, 브라우저 자동 열림)
       python app.py --lan        -> 같은 Wi-Fi의 다른 기기에서도 접속
       python app.py --port 9000  -> 다른 포트 사용
       python app.py --no-browser -> 브라우저를 자동으로 열지 않음
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

YEAR = 31_557_600          # 365.25일
FAST = 1e10                # 유출 DB + 빠른 해시 + GPU: 초당 100억 회
SAMPLE = "qwer1234"
MAX_LEN = 128

# 흔한 한국어 단어: 영문 자판(두벌식)으로 친 것과 한글 그대로
KO_WORDS = [
    "dkssud", "dkssudgktpdy", "tkfkd", "tkfkdgo", "tkfkdgody", "qlalfqjsgh", "qlqjs", "gksrmf",
    "eogksalsrnr", "dnflskfk", "godqhr", "ghkdlxld", "djaak", "rkwhr", "clsrn",
    "안녕하세요", "안녕", "사랑해요", "사랑해", "사랑", "비밀번호", "비번", "대한민국", "우리나라",
    "행복", "화이팅", "가족", "친구",
]

SCENARIOS = [
    ("로그인 창에 직접 대입", "시도 횟수 제한이 있는 사이트", "시간당 100회", 100 / 3600),
    ("로그인 창에 직접 대입", "횟수 제한이 없는 사이트", "초당 10회", 10.0),
    ("유출된 DB 오프라인 공격", "느린 해시(bcrypt 등)로 저장", "초당 1만 회", 1e4),
    ("유출된 DB 오프라인 공격", "빠른 해시(MD5, SHA-1)로 저장", "초당 100억 회", FAST),
]

HANGUL = "가-힣ㄱ-ㅎㅏ-ㅣ"


# ---------------------------------------------------------------- 진단
def cardinality(pw: str) -> int:
    """공격자가 한 글자마다 시도해야 하는 문자 종류 수."""
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
        extra += " · a→@ 같은 글자 바꿔치기는 공격자도 기본으로 시도합니다"
    if m.get("reversed"):
        extra += " · 뒤집어 써도 마찬가지입니다"
    pattern, token = m["pattern"], m["token"]
    if pattern == "dictionary":
        name = m.get("dictionary_name", "")
        if name == "passwords":
            return f"유출 목록에 자주 나오는 비밀번호 ({m.get('rank')}위){extra}", token
        if name == "user_inputs":
            return f"흔한 한국어 단어 (한글 그대로 또는 영문 자판으로 친 것){extra}", token
        if "names" in name:
            return f"흔한 이름{extra}", token
        return f"사전에 있는 영어 단어{extra}", token
    return {
        "spatial": ("키보드에서 나란히 붙은 키 배열", token),
        "repeat": ("같은 글자나 묶음의 반복", token),
        "sequence": ("순서대로 이어지는 글자나 숫자", token),
        "regex": ("연도로 보이는 숫자", token),
        "date": ("날짜로 보이는 숫자", token),
    }.get(pattern)


def analyze(pw: str):
    """(추정 대입 횟수, 이유 목록)을 돌려준다."""
    card = cardinality(pw)
    head, tail = pw[:72], pw[72:]          # zxcvbn은 72자까지만 받는다
    result = zxcvbn(head, user_inputs=KO_WORDS)

    # zxcvbn은 무작위 구간을 글자당 10가지로만 치므로 실제 문자 종류 수로 다시 계산한다.
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
        reasons.append({"text": f"길이가 {len(pw)}자로 짧습니다. 12자 이상을 권장합니다", "token": None})
    if not reasons:
        reasons.append({"text": "알려진 단어나 패턴이 발견되지 않았습니다", "token": None})
    return guesses, reasons


# ---------------------------------------------------------------- 시간 표시
def seconds(guesses: int, rate: float) -> float:
    try:
        return float(guesses) / rate
    except OverflowError:
        return math.inf


def big_years(y: float) -> str:
    if math.isinf(y) or y >= 1e24:
        return "우주 나이의 수조 배 이상"
    for unit, name in ((1e20, "해"), (1e16, "경"), (1e12, "조"), (1e8, "억"), (1e4, "만")):
        if y >= unit:
            v = y / unit
            num = f"{v:.1f}".rstrip("0").rstrip(".") if v < 100 else f"{round(v):,}"
            return f"약 {num}{name} 년"
    return f"{round(y):,}년"


def split(s: float):
    y, s = divmod(s, YEAR)
    d, s = divmod(s, 86400)
    h, s = divmod(s, 3600)
    m, s = divmod(s, 60)
    return [int(y), int(d), int(h), int(m), int(s)]


UNITS = ["년", "일", "시간", "분", "초"]


def is_huge(s: float) -> bool:
    return math.isinf(s) or s / YEAR >= 10000


def time_text(s: float) -> str:
    if s < 1:
        return "1초 미만"
    if is_huge(s):
        return big_years(s / YEAR)
    parts = split(s)
    i = next(k for k, v in enumerate(parts) if v > 0)
    out = [f"{parts[i]:,}{UNITS[i]}"]
    if i + 1 < 5 and parts[i + 1] > 0:
        out.append(f"{parts[i + 1]}{UNITS[i + 1]}")
    return " ".join(out)


def clock(s: float) -> dict:
    if s < 1:
        return {"single": "1초도 안 걸려요"}
    if is_huge(s):
        return {"single": big_years(s / YEAR)}
    cells, leading = [], True
    for i, v in enumerate(split(s)):
        if v > 0:
            leading = False
        cells.append({"value": f"{v:02d}" if i >= 2 else str(v), "unit": UNITS[i], "zero": leading})
    return {"cells": cells}


def verdict(s: float):
    if s < 60:
        return "crit", "즉시 뚫림"
    if s < 86400:
        return "crit", "매우 약함"
    if s < YEAR:
        return "warn", "약함"
    if s < YEAR * 100:
        return "warn", "보통"
    return "ok", "강함"


# ---------------------------------------------------------------- 생성
SETS = {
    "lower": "abcdefghijklmnopqrstuvwxyz",
    "upper": "ABCDEFGHIJKLMNOPQRSTUVWXYZ",
    "digit": "0123456789",
    "symbol": "!@#$%^&*()-_=+[]{};:,.?/~",
}
AMBIGUOUS = set("0OoIl1|")


def generate(length: int, kinds: list, no_ambiguous: bool):
    """secrets 모듈(운영체제 암호학적 난수)로 비밀번호를 만든다."""
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
        if all(any(ch in g for ch in pw) for g in groups):   # 고른 종류가 모두 들어갈 때까지
            return pw, len(pool)


# ---------------------------------------------------------------- 웹 서버
app = Flask(__name__, static_folder=None)
app.config["MAX_CONTENT_LENGTH"] = 4096


# 공개했을 때를 대비한 간단한 요청 제한: 한 사람당 10초에 150번까지
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
        return jsonify(error="요청이 너무 많아요. 잠시 후 다시 시도하세요."), 429
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
    pw = typed or SAMPLE                     # 비어 있으면 예시를 보여 준다
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


# ---------------------------------------------------------------- HTTPS 인증서
def lan_ip():
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))      # 실제로 패킷을 보내지는 않는다
            return s.getsockname()[0]
    except OSError:
        return None


def ensure_cert():
    """처음 실행할 때 자체 서명 인증서를 만들어 certs/ 에 보관한다."""
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
    parser = argparse.ArgumentParser(description="비밀번호 금고지기 HTTPS 서버")
    parser.add_argument("--port", type=int, default=8443)
    parser.add_argument("--lan", action="store_true", help="같은 네트워크의 다른 기기에서도 접속 허용")
    parser.add_argument("--no-browser", action="store_true", help="브라우저를 자동으로 열지 않음")
    args = parser.parse_args()

    try:                                   # 한글을 못 찍는 콘솔에서도 멈추지 않게
        sys.stdout.reconfigure(errors="replace")
    except (AttributeError, ValueError):
        pass
    if not args.no_browser:
        threading.Timer(1.5, webbrowser.open, [f"https://localhost:{args.port}"]).start()

    host = "0.0.0.0" if args.lan else "127.0.0.1"
    print(f"\n  비밀번호 금고지기  ->  https://localhost:{args.port}")
    if args.lan and lan_ip():
        print(f"  다른 기기에서     ->  https://{lan_ip()}:{args.port}")
    print("  (자체 서명 인증서라 처음 열 때 브라우저 경고가 뜹니다. '고급 > 계속'을 누르세요)\n")
    app.run(host=host, port=args.port, ssl_context=ensure_cert())


if __name__ == "__main__":
    main()
