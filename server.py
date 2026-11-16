"""
Secure Backend Server for Aufbruch – Alumni Conclave 2026
Provides:
- Static file serving for Index.html, fonts/, and assets
- Public registration API: POST /api/register
- Backend Admin Authentication & Session Management:
  - POST /api/admin/login
  - POST /api/admin/logout
  - GET  /api/admin/session
- Protected Admin API Routes (HTTP 401 Unauthorized without valid session):
  - GET  /api/admin/dashboard
  - POST /api/admin/seed
"""

import base64
import hashlib
import hmac
import http.cookies
import io
import json
import mimetypes
import os
import re
import secrets
import socket
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

try:
    from vercel.blob import sync as vercel_blob
except Exception:
    vercel_blob = None

WORKSPACE_DIR = Path(__file__).resolve().parent
PUBLIC_DIR = WORKSPACE_DIR / "public"
BUNDLED_DB_FILE = WORKSPACE_DIR / "registrations_db.json"
ALUMNI_EXCEL_FILE = WORKSPACE_DIR / "alumni list.xlsx"
BUNDLED_STUDENTS_FILE = WORKSPACE_DIR / "alumni_students_db.json"
KV_RECORDS_KEY = os.environ.get("KV_RECORDS_KEY", "aufbruch:registrations_v1")
KV_STUDENTS_KEY = os.environ.get("KV_STUDENTS_KEY", "aufbruch:students_v1")
BLOB_RECORDS_PATH = os.environ.get("BLOB_RECORDS_PATH", "aufbruch/registrations_v1.json")
BLOB_STUDENTS_PATH = os.environ.get("BLOB_STUDENTS_PATH", "aufbruch/students_v1.json")
BLOB_REVOKED_PATH = os.environ.get("BLOB_REVOKED_PATH", "aufbruch/revoked_sessions_v1.json")

BATCH_YEARS = [str(y) for y in range(2001, 2027)]
OFFICIAL_BATCH_TOTALS: dict[str, int] = {
    "2001": 4,
    "2002": 4,
    "2003": 3,
    "2004": 8,
    "2005": 10,
    "2006": 4,
    "2007": 6,
    "2008": 6,
    "2009": 3,
    "2010": 8,
    "2011": 6,
    "2012": 6,
    "2013": 8,
    "2014": 9,
    "2015": 14,
    "2016": 4,
    "2017": 13,
    "2018": 17,
    "2019": 15,
    "2020": 23,
    "2021": 24,
    "2022": 24,
    "2023": 27,
    "2024": 16,
    "2025": 29,
    "2026": 12,
}
OFFICIAL_OVERALL_TOTAL = 330
WHATSAPP_SENDER_NUMBER = os.environ.get("WHATSAPP_SENDER_NUMBER", "8606140996").strip()


def _resolve_index_html() -> Path:
    for candidate in (
        PUBLIC_DIR / "index.html",
        WORKSPACE_DIR / "index.html",
        WORKSPACE_DIR / "Index.html",
    ):
        if candidate.exists() and candidate.is_file():
            return candidate
    return PUBLIC_DIR / "index.html"


def _get_kv_config() -> tuple[str, str] | None:
    url = (
        os.environ.get("KV_REST_API_URL", "").strip()
        or os.environ.get("UPSTASH_REDIS_REST_URL", "").strip()
    )
    token = (
        os.environ.get("KV_REST_API_TOKEN", "").strip()
        or os.environ.get("UPSTASH_REDIS_REST_TOKEN", "").strip()
    )
    if url and token:
        return (url.rstrip("/"), token)
    return None


def _kv_command(cmd: list):
    cfg = _get_kv_config()
    if not cfg:
        raise RuntimeError("KV REST configuration is not set.")
    kv_url, kv_token = cfg
    req = urllib.request.Request(
        kv_url,
        data=json.dumps(cmd).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {kv_token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=8) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
        if isinstance(payload, dict) and payload.get("error"):
            raise RuntimeError(f"KV error: {payload['error']}")
        return payload.get("result") if isinstance(payload, dict) else None


def _get_blob_config() -> bool:
    return bool(os.environ.get("BLOB_READ_WRITE_TOKEN", "").strip() and vercel_blob is not None)


def _blob_load_json(pathname: str):
    if not _get_blob_config():
        return None
    not_found_exc = getattr(vercel_blob, "BlobNotFoundError", FileNotFoundError)
    try:
        res = vercel_blob.get_blob(pathname, access="private")
        raw = res.body.decode("utf-8") if isinstance(res.body, (bytes, bytearray)) else str(res.body)
        return json.loads(raw)
    except (not_found_exc, FileNotFoundError):
        return None


def _blob_save_json(pathname: str, payload_text: str) -> None:
    if not _get_blob_config():
        raise RuntimeError("Vercel Blob storage is not configured.")
    vercel_blob.put_blob(
        pathname,
        payload_text.encode("utf-8"),
        access="private",
        content_type="application/json",
        add_random_suffix=False,
        allow_overwrite=True,
        cache_control_max_age=0,
    )


def get_storage_mode() -> str:
    if _get_kv_config():
        return "vercel-kv"
    if _get_blob_config():
        return "vercel-blob"
    if os.environ.get("DB_FILE", "").strip() or os.access(WORKSPACE_DIR, os.W_OK):
        return "local-file"
    return "tmp-ephemeral"


def _resolve_db_file() -> Path:
    env_db = os.environ.get("DB_FILE", "").strip()
    if env_db:
        return Path(env_db)
    # Use workspace file whenever directory is writable; fall back to tmp only on read-only serverless hosts
    if os.access(WORKSPACE_DIR, os.W_OK):
        return BUNDLED_DB_FILE
    tmp_db = Path(tempfile.gettempdir()) / "aufbruch_registrations_db.json"
    if not tmp_db.exists() and BUNDLED_DB_FILE.exists():
        try:
            tmp_db.write_text(BUNDLED_DB_FILE.read_text(encoding="utf-8"), encoding="utf-8")
        except Exception:
            pass
    return tmp_db


def _resolve_students_file() -> Path:
    env_st = os.environ.get("STUDENTS_FILE", "").strip()
    if env_st:
        return Path(env_st)
    if os.access(WORKSPACE_DIR, os.W_OK):
        return BUNDLED_STUDENTS_FILE
    tmp_st = Path(tempfile.gettempdir()) / "aufbruch_students_db.json"
    if not tmp_st.exists() and BUNDLED_STUDENTS_FILE.exists():
        try:
            tmp_st.write_text(BUNDLED_STUDENTS_FILE.read_text(encoding="utf-8"), encoding="utf-8")
        except Exception:
            pass
    return tmp_st


DB_FILE = _resolve_db_file()
STUDENTS_FILE = _resolve_students_file()

# ============================================================================
# SERVER-SIDE ADMIN CREDENTIALS (PBKDF2-HMAC-SHA256)
# Never exposed in frontend HTML or JavaScript.
# Default Username: admin
# Default Password: Aufbruch@2026 (can be overridden via ADMIN_USERNAME / ADMIN_PASSWORD env vars)
# ============================================================================
ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
_ADMIN_SALT = b"aufbruch_2026_majmau_secure_salt_v1"
_DEFAULT_PASSWORD = os.environ.get("ADMIN_PASSWORD", "Aufbruch@2026")
ADMIN_PASSWORD_HASH = hashlib.pbkdf2_hmac(
    "sha256", _DEFAULT_PASSWORD.encode("utf-8"), _ADMIN_SALT, 120_000
).hex()

# Active server-side sessions + persistent HMAC signing (survives restarts/workers)
ACTIVE_SESSIONS: dict[str, dict] = {}
REVOKED_TOKENS: set[str] = set()
REVOKED_FILE = (
    WORKSPACE_DIR / ".aufbruch_revoked_sessions.json"
    if os.access(WORKSPACE_DIR, os.W_OK)
    else Path(tempfile.gettempdir()) / ".aufbruch_revoked_sessions.json"
)
SESSION_TTL_SECONDS = 8 * 3600  # 8 hours
SESSION_COOKIE_NAME = "aufbruch_admin_session"


def _get_session_signing_key() -> bytes:
    env_secret = os.environ.get("SESSION_SECRET", "").strip()
    if env_secret:
        return hashlib.sha256(env_secret.encode("utf-8")).digest()
    return hmac.new(_ADMIN_SALT, ADMIN_PASSWORD_HASH.encode("utf-8"), hashlib.sha256).digest()


def _load_revoked_tokens() -> dict[str, int]:
    now = int(time.time())
    revoked_map: dict[str, int] = {}
    if REVOKED_FILE.exists():
        try:
            raw = json.loads(REVOKED_FILE.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                revoked_map = {k: int(v) for k, v in raw.items() if int(v) > now}
        except Exception:
            revoked_map = {}
    return revoked_map


def _mark_token_revoked(jti: str, exp: int) -> None:
    if not jti:
        return
    REVOKED_TOKENS.add(jti)
    now = int(time.time())
    if _get_kv_config():
        ttl = max(60, int(exp - now))
        try:
            _kv_command(["SET", f"aufbruch:revoked_jti:{jti}", "1", "EX", str(ttl)])
        except Exception:
            pass
    elif _get_blob_config():
        try:
            existing = _blob_load_json(BLOB_REVOKED_PATH)
            blob_map = (
                {k: int(v) for k, v in existing.items() if int(v) > now}
                if isinstance(existing, dict)
                else {}
            )
            blob_map[jti] = exp
            _blob_save_json(BLOB_REVOKED_PATH, json.dumps(blob_map))
        except Exception:
            pass
    revoked_map = _load_revoked_tokens()
    revoked_map[jti] = exp
    try:
        REVOKED_FILE.write_text(json.dumps(revoked_map), encoding="utf-8")
    except Exception:
        pass


def _is_jti_revoked(jti: str) -> bool:
    if not jti:
        return True
    if jti in REVOKED_TOKENS:
        return True
    if _get_kv_config():
        try:
            res = _kv_command(["GET", f"aufbruch:revoked_jti:{jti}"])
            if res is not None:
                REVOKED_TOKENS.add(jti)
                return True
        except Exception:
            pass
    elif _get_blob_config():
        try:
            now = int(time.time())
            existing = _blob_load_json(BLOB_REVOKED_PATH)
            if isinstance(existing, dict) and jti in existing and int(existing[jti]) > now:
                REVOKED_TOKENS.add(jti)
                return True
        except Exception:
            pass
    revoked_map = _load_revoked_tokens()
    if jti in revoked_map:
        REVOKED_TOKENS.add(jti)
        return True
    return False

EXACT_CONFIRMATION_MESSAGE = (
    "Registration Successful!\n\n"
    "Thank you for registering for Aufbruch – Alumni Conclave 2026."
)

DEFAULT_SEED_DATA = [
    {
        "registrationId": "001",
        "timestamp": "2026-11-12 09:15:22",
        "name": "Muhammed Anwar",
        "place": "Nilambur",
        "batchYear": "2016",
        "whatsappNumber": "+91 98470 11223",
        "participation": "പങ്കെടുക്കും",
    },
    {
        "registrationId": "002",
        "timestamp": "2026-11-12 09:32:10",
        "name": "Dr. Salman Faris",
        "place": "Manjeri",
        "batchYear": "2014",
        "whatsappNumber": "9895123456",
        "participation": "പങ്കെടുക്കും",
    },
    {
        "registrationId": "003",
        "timestamp": "2026-11-12 09:48:05",
        "name": "Abdul Rasheed K",
        "place": "Malappuram",
        "batchYear": "2018",
        "whatsappNumber": "+91 94471 88990",
        "participation": "സാധിക്കില്ല",
    },
    {
        "registrationId": "004",
        "timestamp": "2026-11-12 10:05:41",
        "name": "Shameer Ali P",
        "place": "Nilambur",
        "batchYear": "2018",
        "whatsappNumber": "9745098765",
        "participation": "പങ്കെടുക്കും",
    },
    {
        "registrationId": "005",
        "timestamp": "2026-11-12 10:19:14",
        "name": "Faisal Rahman",
        "place": "Calicut",
        "batchYear": "2015",
        "whatsappNumber": "+91-8086123450",
        "participation": "പങ്കെടുക്കും",
    },
    {
        "registrationId": "006",
        "timestamp": "2026-11-12 10:42:30",
        "name": "Nizamudheen T",
        "place": "Wandoor",
        "batchYear": "2020",
        "whatsappNumber": "9633112244",
        "participation": "പങ്കെടുക്കും",
    },
]


def normalize_indian_phone(raw_input: str) -> dict:
    if raw_input is None:
        return {"isValid": False, "error": "Phone number is required."}
    s = str(raw_input).strip()
    cleaned = re.sub(r"[\s\-\.\(\)]", "", s)

    national = cleaned
    if national.startswith("+91"):
        national = national[3:]
    elif len(national) == 12 and national.startswith("91"):
        national = national[2:]
    elif len(national) == 11 and national.startswith("0"):
        national = national[1:]

    if not re.match(r"^[6-9]\d{9}$", national):
        return {
            "isValid": False,
            "raw": s,
            "error": "Please enter a valid 10-digit Indian WhatsApp number (with or without +91).",
        }

    return {
        "isValid": True,
        "national": national,
        "waNumber": "91" + national,
        "e164": "+91" + national,
        "display": f"+91 {national[:5]} {national[5:]}",
        "error": None,
    }


def build_whatsapp_message(name: str) -> str:
    clean_name = str(name or "Alumni Member").strip() or "Alumni Member"
    return (
        "അസ്സലാമു അലൈകും\n\n"
        f"Hi... *{clean_name}*\n\n"
        "നിങ്ങൾ അൻവാർ അലുംനി കോൺക്ലൈവിൽ രജിസ്റ്റർ ചെയ്തതിന് നന്ദി...\n\n"
        "*ഡിസംബർ 10 വൈകിട്ട് 3:30 മുതൽ രാത്രി 9:30 വരെ* നടക്കുന്ന സംഗമത്തിൽ പങ്കാളിത്തം ഉറപ്പ് വരുത്തുക."
    )


def format_anwar_id(raw_id_or_num) -> str:
    s = str(raw_id_or_num or "001").strip()
    m = re.search(r"(\d+)$", s)
    num = int(m.group(1)) if m else 1
    return f"ANWAR {num:03d}"


def normalize_reg_id(raw_id_or_num) -> str:
    s = str(raw_id_or_num or "001").strip()
    m = re.search(r"(\d+)$", s)
    num = int(m.group(1)) if m else 1
    return f"{num:03d}"


def generate_ticket_token(reg_id: str) -> str:
    clean_id = normalize_reg_id(reg_id)
    mac = hmac.new(
        _get_session_signing_key(),
        f"aufbruch_ticket_2026:{clean_id}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()[:12].upper()
    return f"AUF26-ANWAR{clean_id}-{mac}"


def make_qr_matrix(text: str) -> list[list[int]]:
    data_bytes = str(text or "").encode("utf-8")
    specs = [
        (1, 21, 19, 7, []),
        (2, 25, 34, 10, [6, 18]),
        (3, 29, 55, 15, [6, 22]),
        (4, 33, 80, 20, [6, 26]),
    ]
    for ver, size, total_dcw, ec_len, align_pos in specs:
        if len(data_bytes) <= total_dcw - 2:
            break
    else:
        ver, size, total_dcw, ec_len, align_pos = specs[-1]
        data_bytes = data_bytes[: total_dcw - 2]

    bits = [0, 1, 0, 0]
    n = len(data_bytes)
    for i in range(7, -1, -1):
        bits.append((n >> i) & 1)
    for b in data_bytes:
        for i in range(7, -1, -1):
            bits.append((b >> i) & 1)
    max_bits = total_dcw * 8
    for _ in range(min(4, max_bits - len(bits))):
        bits.append(0)
    while len(bits) % 8 != 0:
        bits.append(0)
    pad_bytes = [0xEC, 0x11]
    pad_idx = 0
    while len(bits) < max_bits:
        pb = pad_bytes[pad_idx % 2]
        pad_idx += 1
        for i in range(7, -1, -1):
            bits.append((pb >> i) & 1)

    dcw = []
    for i in range(0, len(bits), 8):
        val = 0
        for b in bits[i : i + 8]:
            val = (val << 1) | b
        dcw.append(val)

    exp = [0] * 512
    log = [0] * 256
    x = 1
    for i in range(255):
        exp[i] = x
        log[x] = i
        x <<= 1
        if x & 0x100:
            x ^= 0x11D
    for i in range(255, 512):
        exp[i] = exp[i - 255]

    def gf_mul(a: int, b: int) -> int:
        if a == 0 or b == 0:
            return 0
        return exp[log[a] + log[b]]

    gen = [1]
    for i in range(ec_len):
        nxt = [0] * (len(gen) + 1)
        factor = exp[i]
        for j, coeff in enumerate(gen):
            nxt[j] ^= coeff
            nxt[j + 1] ^= gf_mul(coeff, factor)
        gen = nxt

    rem = [0] * ec_len
    for b in dcw:
        factor = b ^ rem[0]
        rem = rem[1:] + [0]
        if factor != 0:
            for j in range(ec_len):
                rem[j] ^= gf_mul(gen[j + 1], factor)

    codewords = dcw + rem
    grid = [[0] * size for _ in range(size)]
    is_func = [[False] * size for _ in range(size)]

    def set_func(r: int, c: int, val: bool):
        if 0 <= r < size and 0 <= c < size:
            grid[r][c] = 1 if val else 0
            is_func[r][c] = True

    def place_finder(row: int, col: int):
        for dr in range(-1, 8):
            for dc in range(-1, 8):
                r, c = row + dr, col + dc
                if 0 <= r < size and 0 <= c < size:
                    in_outer = 0 <= dr <= 6 and (dc in (0, 6) or dr in (0, 6))
                    in_inner = 2 <= dr <= 4 and 2 <= dc <= 4
                    set_func(r, c, in_outer or in_inner)

    place_finder(0, 0)
    place_finder(0, size - 7)
    place_finder(size - 7, 0)

    for i in range(8, size - 8):
        set_func(6, i, i % 2 == 0)
        set_func(i, 6, i % 2 == 0)

    if len(align_pos) >= 2:
        for ar in align_pos:
            for ac in align_pos:
                if (ar < 8 and ac < 8) or (ar < 8 and ac > size - 9) or (ar > size - 9 and ac < 8):
                    continue
                for dr in range(-2, 3):
                    for dc in range(-2, 3):
                        set_func(ar + dr, ac + dc, max(abs(dr), abs(dc)) in (0, 2))

    set_func(4 * ver + 9, 8, True)
    for i in range(9):
        if not is_func[8][i]:
            set_func(8, i, False)
        if not is_func[i][8]:
            set_func(i, 8, False)
    for i in range(8):
        if not is_func[8][size - 1 - i]:
            set_func(8, size - 1 - i, False)
        if not is_func[size - 1 - i][8]:
            set_func(size - 1 - i, 8, False)

    all_bits = []
    for cw in codewords:
        for i in range(7, -1, -1):
            all_bits.append((cw >> i) & 1)

    bit_idx = 0
    up = True
    col = size - 1
    while col > 0:
        if col == 6:
            col -= 1
        row_iter = range(size - 1, -1, -1) if up else range(size)
        for r in row_iter:
            for dc in (0, -1):
                c = col + dc
                if not is_func[r][c]:
                    val = all_bits[bit_idx] if bit_idx < len(all_bits) else 0
                    bit_idx += 1
                    if (r + c) % 2 == 0:
                        val ^= 1
                    grid[r][c] = val
        up = not up
        col -= 2

    fmt = 0x77C4
    fmt_bits = [(fmt >> i) & 1 for i in range(15)]
    tl_coords = [
        (8, 0), (8, 1), (8, 2), (8, 3), (8, 4), (8, 5), (8, 7), (8, 8),
        (7, 8), (5, 8), (4, 8), (3, 8), (2, 8), (1, 8), (0, 8),
    ]
    for idx, (r, c) in enumerate(tl_coords):
        grid[r][c] = fmt_bits[14 - idx]
    for idx in range(7):
        grid[size - 1 - idx][8] = fmt_bits[14 - idx]
    for idx in range(7, 15):
        grid[8][size - 15 + idx] = fmt_bits[14 - idx]

    return grid


def make_qr_svg(text: str, module_px: int = 8, border: int = 4) -> str:
    matrix = make_qr_matrix(text)
    size = len(matrix)
    total_px = (size + border * 2) * module_px
    rects = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {total_px} {total_px}" width="{total_px}" height="{total_px}" shape-rendering="crispEdges">',
        f'<rect width="{total_px}" height="{total_px}" fill="#FFFFFF"/>',
    ]
    for r, row in enumerate(matrix):
        for c, val in enumerate(row):
            if val:
                x = (c + border) * module_px
                y = (r + border) * module_px
                rects.append(f'<rect x="{x}" y="{y}" width="{module_px}" height="{module_px}" fill="#0A1628"/>')
    rects.append("</svg>")
    return "".join(rects)


def parse_alumni_xlsx_bytes(raw_bytes: bytes) -> tuple[list[dict], list[dict]]:
    with zipfile.ZipFile(io.BytesIO(raw_bytes), "r") as z:
        shared_strings: list[str] = []
        if "xl/sharedStrings.xml" in z.namelist():
            root = ET.fromstring(z.read("xl/sharedStrings.xml"))
            ns = {"main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
            for si in root.findall("main:si", ns):
                texts = [t.text or "" for t in si.findall(".//main:t", ns)]
                shared_strings.append("".join(texts))
        sheet_xml = z.read("xl/worksheets/sheet1.xml")
        root = ET.fromstring(sheet_xml)
        ns = {"main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
        rows_out = []
        for row in root.findall(".//main:row", ns):
            cells = {}
            for c in row.findall("main:c", ns):
                ref = c.attrib.get("r", "")
                col = "".join(ch for ch in ref if ch.isalpha())
                t = c.attrib.get("t", "")
                v_el = c.find("main:v", ns)
                is_el = c.find("main:is", ns)
                val = ""
                if t == "s" and v_el is not None and v_el.text is not None:
                    idx = int(v_el.text)
                    val = shared_strings[idx] if idx < len(shared_strings) else ""
                elif t == "inlineStr" and is_el is not None:
                    val = "".join(x.text or "" for x in is_el.findall(".//main:t", ns))
                elif v_el is not None and v_el.text is not None:
                    val = v_el.text
                cells[col] = val
            rows_out.append(cells)

    current_batch = None
    students: list[dict] = []
    seen_batch_names: set[tuple[str, str]] = set()
    removed_duplicates: list[dict] = []
    batch_seq: dict[str, int] = {}

    for r in rows_out:
        vals = [str(r.get(col, "")).strip() for col in sorted(r.keys())]
        joined = " | ".join(vals)
        m = re.search(r"BATCH\s*NO\s*[-–:]?\s*(\d{4})", joined, re.I)
        if m:
            current_batch = m.group(1)
            continue
        b_val = str(r.get("B", "")).strip()
        c_val = str(r.get("C", "")).strip()
        if not c_val or not current_batch:
            continue
        clean_name = re.sub(r"\s+", " ", c_val).strip()
        if not clean_name:
            continue
        sl = None
        if b_val:
            try:
                sl = int(float(b_val))
            except Exception:
                sl = None
        norm_key = (current_batch, sl, clean_name.upper())
        if norm_key in seen_batch_names:
            removed_duplicates.append({"batchYear": current_batch, "serialNo": sl, "name": clean_name})
            continue
        seen_batch_names.add(norm_key)
        batch_seq[current_batch] = batch_seq.get(current_batch, 0) + 1
        seq_num = batch_seq[current_batch]
        stu_id = f"STU-{current_batch}-{sl if sl is not None else seq_num:03d}"
        students.append(
            {
                "studentId": stu_id,
                "serialNo": sl,
                "batchYear": current_batch,
                "name": clean_name,
            }
        )
    return students, removed_duplicates


def _load_seed_students() -> list[dict]:
    if BUNDLED_STUDENTS_FILE.exists():
        try:
            data = json.loads(BUNDLED_STUDENTS_FILE.read_text(encoding="utf-8"))
            if isinstance(data, list) and len(data) > 0:
                return data
        except Exception:
            pass
    if ALUMNI_EXCEL_FILE.exists():
        try:
            students, _ = parse_alumni_xlsx_bytes(ALUMNI_EXCEL_FILE.read_bytes())
            if students:
                return students
        except Exception:
            pass
    return []


def load_students_db() -> list[dict]:
    if _get_kv_config():
        try:
            raw = _kv_command(["GET", KV_STUDENTS_KEY])
            if raw:
                data = json.loads(raw) if isinstance(raw, str) else raw
                if isinstance(data, list) and len(data) > 0:
                    return data
            seeded = _load_seed_students()
            if seeded:
                _kv_command(["SET", KV_STUDENTS_KEY, json.dumps(seeded, ensure_ascii=False)])
            return seeded
        except Exception:
            pass

    if _get_blob_config():
        data = _blob_load_json(BLOB_STUDENTS_PATH)
        if isinstance(data, list) and len(data) > 0:
            return data
        seeded = _load_seed_students()
        if seeded:
            save_students_db(seeded)
        return seeded

    if STUDENTS_FILE.exists():
        try:
            data = json.loads(STUDENTS_FILE.read_text(encoding="utf-8"))
            if isinstance(data, list) and len(data) > 0:
                return data
        except Exception:
            pass
    seeded = _load_seed_students()
    if seeded:
        save_students_db(seeded)
    return seeded


def save_students_db(students: list[dict]) -> None:
    serialized = json.dumps(students, ensure_ascii=False, indent=2)
    if _get_kv_config():
        try:
            _kv_command(["SET", KV_STUDENTS_KEY, serialized])
        except Exception:
            pass
    elif _get_blob_config():
        try:
            _blob_save_json(BLOB_STUDENTS_PATH, serialized)
        except Exception:
            pass
    try:
        STUDENTS_FILE.write_text(serialized, encoding="utf-8")
    except Exception:
        pass


def enrich_registration(rec: dict) -> dict:
    phone_data = normalize_indian_phone(rec.get("whatsappNumber", ""))
    participation = str(rec.get("participation", "")).strip()
    is_participating = participation == "പങ്കെടുക്കും"
    should_send = bool(is_participating and phone_data["isValid"])
    clean_name = re.sub(r"\s+", " ", str(rec.get("name", "")).strip())
    msg = build_whatsapp_message(clean_name) if should_send else ""
    wa_url = (
        f"https://wa.me/{phone_data['waNumber']}?text={urllib.parse.quote(msg, safe='')}"
        if should_send
        else ""
    )

    place_str = str(rec.get("place", "")).strip().title()
    raw_id = normalize_reg_id(rec.get("registrationId") or rec.get("ticketId") or "001")
    ticket_id = format_anwar_id(raw_id)
    ticket_token = str(rec.get("ticketToken") or "").strip() or generate_ticket_token(raw_id)

    orig_excel_name = re.sub(r"\s+", " ", str(rec.get("originalExcelName") or clean_name).strip())
    name_edited = bool(rec.get("nameEdited") or (orig_excel_name and orig_excel_name.upper() != clean_name.upper()))
    student_id = str(rec.get("studentId") or "").strip()

    wa_sent = bool(rec.get("whatsappSent", False))
    wa_sent_at = str(rec.get("whatsappSentAt") or "").strip() if wa_sent else ""
    try:
        wa_sent_count = int(rec.get("whatsappSentCount") or (1 if wa_sent else 0)) if wa_sent else 0
    except (ValueError, TypeError):
        wa_sent_count = 1 if wa_sent else 0

    checked_in = bool(rec.get("checkedIn", False))
    checkin_ts = str(rec.get("checkInTimestamp") or "").strip() if checked_in else ""
    checked_in_by = str(rec.get("checkedInBy") or "").strip() if checked_in else ""

    return {
        "registrationId": raw_id,
        "ticketId": ticket_id,
        "ticketToken": ticket_token,
        "timestamp": rec.get("timestamp") or datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "name": clean_name,
        "originalExcelName": orig_excel_name,
        "nameEdited": name_edited,
        "studentId": student_id,
        "place": place_str,
        "batchYear": str(rec.get("batchYear", "")).strip(),
        "whatsappNumber": str(rec.get("whatsappNumber", "")).strip(),
        "formattedPhone": phone_data["display"] if phone_data["isValid"] else str(rec.get("whatsappNumber", "")),
        "waNumber": phone_data["waNumber"] if phone_data["isValid"] else "",
        "participation": participation,
        "shouldSendWhatsApp": should_send,
        "whatsAppMessage": msg,
        "whatsAppClickToChatUrl": wa_url,
        "whatsappSent": wa_sent,
        "whatsappSentAt": wa_sent_at,
        "whatsappSentCount": wa_sent_count,
        "whatsappCloudApiMessageId": str(rec.get("whatsappCloudApiMessageId") or "").strip(),
        "registrationStatus": "REGISTERED",
        "checkedIn": checked_in,
        "checkInStatus": "CHECKED IN" if checked_in else "NOT CHECKED IN",
        "checkInTimestamp": checkin_ts,
        "checkedInBy": checked_in_by,
        "qrMatrix": make_qr_matrix(ticket_token),
    }


def _load_seed_records() -> list[dict]:
    if BUNDLED_DB_FILE.exists():
        try:
            data = json.loads(BUNDLED_DB_FILE.read_text(encoding="utf-8"))
            if isinstance(data, list) and len(data) > 0:
                return [enrich_registration(r) for r in data]
        except Exception:
            pass
    return [enrich_registration(r) for r in DEFAULT_SEED_DATA]


def load_db() -> list[dict]:
    if _get_kv_config():
        try:
            raw = _kv_command(["GET", KV_RECORDS_KEY])
            if raw:
                data = json.loads(raw) if isinstance(raw, str) else raw
                if isinstance(data, list):
                    return [enrich_registration(r) for r in data]
            seeded = _load_seed_records()
            _kv_command(["SET", KV_RECORDS_KEY, json.dumps(seeded, ensure_ascii=False)])
            return seeded
        except Exception:
            pass

    if _get_blob_config():
        data = _blob_load_json(BLOB_RECORDS_PATH)
        if isinstance(data, list):
            return [enrich_registration(r) for r in data]
        seeded = _load_seed_records()
        save_db(seeded)
        return seeded

    if not DB_FILE.exists():
        seeded = _load_seed_records()
        save_db(seeded)
        return seeded
    try:
        data = json.loads(DB_FILE.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return [enrich_registration(r) for r in data]
    except Exception:
        pass
    seeded = _load_seed_records()
    save_db(seeded)
    return seeded


def save_db(records: list[dict]) -> None:
    serialized = json.dumps(records, ensure_ascii=False, indent=2)
    cloud_saved = False
    if _get_kv_config():
        _kv_command(["SET", KV_RECORDS_KEY, serialized])
        cloud_saved = True
    elif _get_blob_config():
        _blob_save_json(BLOB_RECORDS_PATH, serialized)
        cloud_saved = True
    try:
        DB_FILE.write_text(serialized, encoding="utf-8")
    except Exception as exc:
        if not cloud_saved:
            raise RuntimeError(f"Failed to persist registration database: {exc}") from exc


def _sync_registration_to_gas(record: dict) -> bool:
    gas_url = os.environ.get("GAS_WEBAPP_URL", "").strip()
    if not gas_url:
        return False
    try:
        req = urllib.request.Request(
            gas_url,
            data=json.dumps({"action": "register", **record}, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=6) as resp:
            return 200 <= resp.status < 300
    except Exception:
        return False


def verify_admin_credentials(username: str, password: str) -> bool:
    if not username or not password:
        return False
    user_ok = hmac.compare_digest(username.strip(), ADMIN_USERNAME)
    candidate_hash = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), _ADMIN_SALT, 120_000
    ).hex()
    pass_ok = hmac.compare_digest(candidate_hash, ADMIN_PASSWORD_HASH)
    return user_ok and pass_ok


def create_session(username: str) -> str:
    now = int(time.time())
    exp = now + SESSION_TTL_SECONDS
    jti = secrets.token_hex(12)
    payload_bytes = json.dumps({"u": username, "exp": exp, "jti": jti}, separators=(",", ":")).encode("utf-8")
    b64 = base64.urlsafe_b64encode(payload_bytes).decode("ascii").rstrip("=")
    sig = hmac.new(_get_session_signing_key(), b64.encode("ascii"), hashlib.sha256).hexdigest()
    token = f"{b64}.{sig}"
    ACTIVE_SESSIONS[token] = {
        "username": username,
        "expires_at": float(exp),
        "jti": jti,
    }
    return token


def _verify_signed_token(token: str) -> dict | None:
    if not token or "." not in token:
        return None
    parts = token.split(".", 1)
    if len(parts) != 2:
        return None
    b64, sig = parts
    expected_sig = hmac.new(_get_session_signing_key(), b64.encode("ascii"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected_sig):
        return None
    try:
        padded = b64 + "=" * (-len(b64) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8"))
        username = str(payload.get("u", "")).strip()
        exp = float(payload.get("exp", 0))
        jti = str(payload.get("jti", "")).strip()
    except Exception:
        return None

    if not username or not hmac.compare_digest(username, ADMIN_USERNAME):
        return None
    if time.time() > exp or _is_jti_revoked(jti):
        ACTIVE_SESSIONS.pop(token, None)
        return None

    return {"token": token, "username": username, "expires_at": exp, "jti": jti}


def revoke_session(token: str) -> None:
    if not token:
        return
    sess = ACTIVE_SESSIONS.pop(token, None) or _verify_signed_token(token)
    if sess:
        _mark_token_revoked(str(sess.get("jti", "")), int(sess.get("expires_at", time.time() + SESSION_TTL_SECONDS)))


def get_valid_session(handler: BaseHTTPRequestHandler) -> dict | None:
    candidates: list[str] = []

    # 1. Check Authorization Bearer header
    auth_header = handler.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        bearer_tok = auth_header[7:].strip()
        if bearer_tok:
            candidates.append(bearer_tok)

    # 2. Check HttpOnly Cookie
    cookie_header = handler.headers.get("Cookie", "")
    if cookie_header:
        jar = http.cookies.SimpleCookie()
        try:
            jar.load(cookie_header)
            if SESSION_COOKIE_NAME in jar:
                cookie_tok = jar[SESSION_COOKIE_NAME].value
                if cookie_tok and cookie_tok not in candidates:
                    candidates.append(cookie_tok)
        except Exception:
            pass

    for token in candidates:
        verified = _verify_signed_token(token)
        if verified:
            ACTIVE_SESSIONS[token] = verified
            return verified

    return None


def format_pct(reg_count: int, total_count: int) -> str:
    if total_count <= 0:
        return "0%"
    val = round((reg_count / total_count) * 100, 1)
    if val == int(val):
        return f"{int(val)}%"
    return f"{val}%"


def build_batch_report_data(records: list[dict], students: list[dict]) -> dict:
    # Count unique registered students per batch (deduplicated by batchYear + originalExcelName/name)
    unique_reg_by_batch: dict[str, set[str]] = {y: set() for y in BATCH_YEARS}
    unique_checkin_by_batch: dict[str, set[str]] = {y: set() for y in BATCH_YEARS}
    excel_count_by_batch: dict[str, int] = {y: 0 for y in BATCH_YEARS}

    for st in students:
        by = str(st.get("batchYear", "")).strip()
        if by in excel_count_by_batch:
            excel_count_by_batch[by] += 1

    for r in records:
        by = str(r.get("batchYear", "")).strip()
        stu_id = str(r.get("studentId") or "").strip()
        key_name = re.sub(r"\s+", " ", str(r.get("originalExcelName") or r.get("name") or "").strip()).upper()
        if not key_name and not stu_id:
            continue
        uniq_token = f"STU:{stu_id}" if stu_id else f"NAME:{key_name}"
        if by in unique_reg_by_batch:
            unique_reg_by_batch[by].add(uniq_token)
            if r.get("checkedIn"):
                unique_checkin_by_batch[by].add(uniq_token)

    batch_rows: list[dict] = []
    report_lines: list[str] = [
        "*Aufbruch*",
        "*Alumni Conclave 2026*",
        "________________________",
        "",
    ]

    total_unique_registered = 0
    for idx, year in enumerate(BATCH_YEARS, start=1):
        reg_cnt = len(unique_reg_by_batch[year])
        total_unique_registered += reg_cnt
        off_tot = OFFICIAL_BATCH_TOTALS.get(year, 0)
        excel_cnt = excel_count_by_batch.get(year, 0)
        checkin_cnt = len(unique_checkin_by_batch[year])
        pct_num = round((reg_cnt / off_tot) * 100, 1) if off_tot > 0 else 0.0
        pct_str = format_pct(reg_cnt, off_tot)
        line = f"{idx}. Batch {year} : {reg_cnt:02d}/{off_tot:02d} ({pct_str})"
        report_lines.append(line)
        batch_rows.append(
            {
                "index": idx,
                "batchYear": year,
                "registeredCount": reg_cnt,
                "registeredFormatted": f"{reg_cnt:02d}",
                "officialTotal": off_tot,
                "officialTotalFormatted": f"{off_tot:02d}",
                "excelImportedCount": excel_cnt,
                "discrepancy": off_tot - excel_cnt,
                "percentage": pct_num,
                "percentageFormatted": pct_str,
                "checkedInCount": checkin_cnt,
                "pendingCheckInCount": max(0, reg_cnt - checkin_cnt),
                "reportLine": line,
            }
        )

    overall_pct_num = round((total_unique_registered / OFFICIAL_OVERALL_TOTAL) * 100, 1)
    overall_pct_str = format_pct(total_unique_registered, OFFICIAL_OVERALL_TOTAL)
    overall_line = f"*Total Registration: {total_unique_registered:02d}/{OFFICIAL_OVERALL_TOTAL} ({overall_pct_str})*"
    report_lines.append("")
    report_lines.append("________________________")
    report_lines.append(overall_line)

    discrepancies = [
        {
            "batchYear": b["batchYear"],
            "excelCount": b["excelImportedCount"],
            "officialTotal": b["officialTotal"],
            "missingInExcel": b["discrepancy"],
        }
        for b in batch_rows
        if b["discrepancy"] != 0
    ]

    return {
        "batches": batch_rows,
        "totalRegistered": total_unique_registered,
        "totalRegisteredFormatted": f"{total_unique_registered:02d}",
        "officialOverallTotal": OFFICIAL_OVERALL_TOTAL,
        "overallPercentage": overall_pct_num,
        "overallPercentageFormatted": overall_pct_str,
        "overallSummaryText": f"{total_unique_registered:02d}/{OFFICIAL_OVERALL_TOTAL} ({overall_pct_str})",
        "whatsappReportText": "\n".join(report_lines),
        "discrepancies": discrepancies,
    }


def get_whatsapp_cloud_api_status() -> dict:
    token = os.environ.get("WHATSAPP_CLOUD_API_TOKEN", "").strip()
    phone_id = os.environ.get("WHATSAPP_PHONE_NUMBER_ID", "").strip()
    api_ver = os.environ.get("WHATSAPP_API_VERSION", "v21.0").strip()
    configured = bool(token and phone_id)
    return {
        "senderNumber": WHATSAPP_SENDER_NUMBER,
        "formattedSender": f"+91 {WHATSAPP_SENDER_NUMBER[:5]} {WHATSAPP_SENDER_NUMBER[5:]}" if len(WHATSAPP_SENDER_NUMBER) == 10 else WHATSAPP_SENDER_NUMBER,
        "configured": configured,
        "tokenConfigured": bool(token),
        "phoneNumberIdConfigured": bool(phone_id),
        "apiVersion": api_ver,
        "status": "configured" if configured else "credentials_missing",
        "setupNotice": (
            f"WhatsApp Business Cloud API is configured for sender {WHATSAPP_SENDER_NUMBER}."
            if configured
            else (
                f"Sender number {WHATSAPP_SENDER_NUMBER} is configured, but Meta WhatsApp Business Cloud API "
                "credentials (WHATSAPP_CLOUD_API_TOKEN and WHATSAPP_PHONE_NUMBER_ID) are not set in environment "
                "variables yet. Manual Click-to-Chat (wa.me) remains active; add those environment variables to "
                f"enable automated server-side sending from {WHATSAPP_SENDER_NUMBER}."
            )
        ),
    }


def send_whatsapp_cloud_api_message(recipient_wa_number: str, message_text: str) -> dict:
    cfg = get_whatsapp_cloud_api_status()
    token = os.environ.get("WHATSAPP_CLOUD_API_TOKEN", "").strip()
    phone_id = os.environ.get("WHATSAPP_PHONE_NUMBER_ID", "").strip()
    api_ver = cfg["apiVersion"]
    if not cfg["configured"]:
        return {
            "success": False,
            "configured": False,
            "sent": False,
            "senderNumber": WHATSAPP_SENDER_NUMBER,
            "error": cfg["setupNotice"],
        }
    url = f"https://graph.facebook.com/{api_ver}/{phone_id}/messages"
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": recipient_wa_number,
        "type": "text",
        "text": {"preview_url": False, "body": message_text},
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            res_data = json.loads(resp.read().decode("utf-8"))
            msgs = res_data.get("messages") if isinstance(res_data, dict) else None
            msg_id = msgs[0].get("id") if (isinstance(msgs, list) and msgs and isinstance(msgs[0], dict)) else ""
            if 200 <= resp.status < 300 and msg_id:
                return {
                    "success": True,
                    "configured": True,
                    "sent": True,
                    "senderNumber": WHATSAPP_SENDER_NUMBER,
                    "messageId": msg_id,
                }
            return {
                "success": False,
                "configured": True,
                "sent": False,
                "senderNumber": WHATSAPP_SENDER_NUMBER,
                "error": "Meta Graph API did not return a confirmed message ID.",
            }
    except urllib.error.HTTPError as err:
        err_body = err.read().decode("utf-8", errors="ignore")
        return {
            "success": False,
            "configured": True,
            "sent": False,
            "senderNumber": WHATSAPP_SENDER_NUMBER,
            "error": f"Meta WhatsApp Cloud API HTTP {err.code}: {err_body[:240]}",
        }
    except Exception as exc:
        return {
            "success": False,
            "configured": True,
            "sent": False,
            "senderNumber": WHATSAPP_SENDER_NUMBER,
            "error": f"WhatsApp Cloud API request failed: {exc}",
        }


def build_checkin_xlsx_bytes(records: list[dict]) -> bytes:
    headers = [
        "ID Number",
        "Reg ID",
        "Participant Name",
        "Original Excel Name",
        "Batch Year",
        "Place",
        "WhatsApp (+91)",
        "Participation",
        "Registration Status",
        "Check-in Status",
        "Check-in Date & Time",
        "Confirmed By Admin",
        "Ticket Token",
        "Submitted Timestamp",
    ]
    rows_data = [headers]
    for r in records:
        rows_data.append(
            [
                str(r.get("ticketId") or ""),
                str(r.get("registrationId") or ""),
                str(r.get("name") or ""),
                str(r.get("originalExcelName") or r.get("name") or ""),
                str(r.get("batchYear") or ""),
                str(r.get("place") or ""),
                str(r.get("formattedPhone") or r.get("whatsappNumber") or ""),
                str(r.get("participation") or ""),
                str(r.get("registrationStatus") or "REGISTERED"),
                str(r.get("checkInStatus") or ("CHECKED IN" if r.get("checkedIn") else "NOT CHECKED IN")),
                str(r.get("checkInTimestamp") or "-"),
                str(r.get("checkedInBy") or "-"),
                str(r.get("ticketToken") or ""),
                str(r.get("timestamp") or ""),
            ]
        )

    def xml_escape(s: str) -> str:
        return (
            str(s or "")
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
        )

    def col_letter(idx0: int) -> str:
        res = ""
        n = idx0 + 1
        while n > 0:
            n, rem = divmod(n - 1, 26)
            res = chr(65 + rem) + res
        return res

    sheet_rows_xml = []
    for r_idx, row_vals in enumerate(rows_data, start=1):
        cells_xml = []
        for c_idx, val in enumerate(row_vals):
            ref = f"{col_letter(c_idx)}{r_idx}"
            cells_xml.append(
                f'<c r="{ref}" t="inlineStr"><is><t>{xml_escape(val)}</t></is></c>'
            )
        sheet_rows_xml.append(f'<row r="{r_idx}">{"".join(cells_xml)}</row>')

    sheet_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f'<sheetData>{"".join(sheet_rows_xml)}</sheetData>'
        "</worksheet>"
    )
    content_types_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        "</Types>"
    )
    rels_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
        "</Relationships>"
    )
    workbook_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<sheets><sheet name="Check-in Report" sheetId="1" r:id="rId1"/></sheets>'
        "</workbook>"
    )
    workbook_rels_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
        "</Relationships>"
    )

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", content_types_xml)
        zf.writestr("_rels/.rels", rels_xml)
        zf.writestr("xl/workbook.xml", workbook_xml)
        zf.writestr("xl/_rels/workbook.xml.rels", workbook_rels_xml)
        zf.writestr("xl/worksheets/sheet1.xml", sheet_xml)
    return buf.getvalue()


def build_dashboard_payload() -> dict:
    records = load_db()
    students = load_students_db()
    total = len(records)
    participating = sum(1 for r in records if r["participation"] == "പങ്കെടുക്കും")
    not_participating = total - participating
    rate = round((participating / total) * 100, 1) if total > 0 else 0

    checked_in_total = sum(1 for r in records if r.get("checkedIn"))
    pending_checkin_total = max(0, total - checked_in_total)

    batch_map: dict[str, dict] = {}
    place_map: dict[str, dict] = {}
    for r in records:
        is_yes = r["participation"] == "പങ്കെടുക്കും"
        b_key = r["batchYear"] or "Unspecified"
        if b_key not in batch_map:
            batch_map[b_key] = {"batchYear": b_key, "total": 0, "yes": 0, "no": 0, "checkedIn": 0}
        batch_map[b_key]["total"] += 1
        if is_yes:
            batch_map[b_key]["yes"] += 1
        else:
            batch_map[b_key]["no"] += 1
        if r.get("checkedIn"):
            batch_map[b_key]["checkedIn"] += 1

        p_key = r["place"] or "Unspecified"
        if p_key not in place_map:
            place_map[p_key] = {"place": p_key, "total": 0, "yes": 0, "no": 0}
        place_map[p_key]["total"] += 1
        if is_yes:
            place_map[p_key]["yes"] += 1
        else:
            place_map[p_key]["no"] += 1

    batch_report = build_batch_report_data(records, students)

    return {
        "success": True,
        "authenticated": True,
        "registrations": records,
        "students": students,
        "officialBatchTotals": OFFICIAL_BATCH_TOTALS,
        "officialOverallTotal": OFFICIAL_OVERALL_TOTAL,
        "batchReport": batch_report,
        "whatsappReportText": batch_report["whatsappReportText"],
        "whatsappCloudApi": get_whatsapp_cloud_api_status(),
        "stats": {
            "total": total,
            "participating": participating,
            "notParticipating": not_participating,
            "confirmationRate": rate,
            "checkedIn": checked_in_total,
            "pendingCheckIn": pending_checkin_total,
            "uniqueBatchRegistered": batch_report["totalRegistered"],
            "officialOverallTotal": OFFICIAL_OVERALL_TOTAL,
            "overallPercentage": batch_report["overallPercentage"],
            "overallPercentageFormatted": batch_report["overallPercentageFormatted"],
        },
        "batchBreakdown": [batch_map[k] for k in sorted(batch_map.keys())],
        "placeBreakdown": [
            place_map[k]
            for k in sorted(place_map.keys(), key=lambda x: place_map[x]["total"], reverse=True)
        ],
    }


class AufbruchRequestHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def _normalize_route(self, raw_path: str) -> str:
        parsed = urllib.parse.urlparse(raw_path or self.path)
        qs = urllib.parse.parse_qs(parsed.query)
        route_override = (qs.get("__route", [""])[0] or "").strip().strip("/")
        clean_path = parsed.path.rstrip("/") or "/"

        if clean_path in ("/api", "/api/index", "/api/index.py"):
            if route_override:
                return f"/api/{route_override}"
            if self.headers:
                for hdr in ("X-Vercel-Original-Url", "X-Forwarded-Uri", "X-Original-Uri"):
                    hdr_val = (self.headers.get(hdr, "") or "").strip()
                    if hdr_val:
                        hdr_path = urllib.parse.urlparse(hdr_val).path.rstrip("/")
                        if "/api/" in hdr_path and hdr_path not in ("/api/index", "/api/index.py"):
                            return hdr_path[hdr_path.find("/api/"):]
            return "/api/health"

        api_idx = clean_path.find("/api/")
        if api_idx != -1:
            return clean_path[api_idx:]
        return clean_path

    def send_error(self, code, message=None, explain=None):
        """Ensure /api/ routes never emit default HTML error pages."""
        path = urllib.parse.urlparse(getattr(self, "path", "") or "").path
        accept = (self.headers.get("Accept", "") if self.headers else "") or ""
        if "/api/" in path or "application/json" in accept:
            self._send_json(
                code,
                {
                    "success": False,
                    "message": message or f"HTTP {code} error",
                    "error": message or f"HTTP {code} error",
                },
            )
            return
        super().send_error(code, message, explain)

    def _send_cors_headers(self):
        origin = (self.headers.get("Origin", "") if self.headers else "") or ""
        if origin and origin != "null":
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Access-Control-Allow-Credentials", "true")
            self.send_header("Vary", "Origin")
        else:
            self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, Accept")

    def _is_https_request(self) -> bool:
        proto = (self.headers.get("X-Forwarded-Proto", "") if self.headers else "") or ""
        return "https" in proto.lower()

    def _build_session_cookie(self, value: str, max_age: int) -> str:
        parts = [
            f"{SESSION_COOKIE_NAME}={value}",
            "HttpOnly",
            "Path=/",
            f"Max-Age={max_age}",
            "SameSite=Lax",
        ]
        if self._is_https_request():
            parts.append("Secure")
        return "; ".join(parts)

    def _send_json(self, status_code: int, payload: dict, extra_headers: list[tuple[str, str]] | None = None):
        out = dict(payload)
        if out.get("success") is False:
            msg = out.get("message") or out.get("error") or "Registration failed. Please try again."
            out["message"] = msg
            out.setdefault("error", msg)
        body = json.dumps(out, ensure_ascii=False).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
        self._send_cors_headers()
        if extra_headers:
            for k, v in extra_headers:
                self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _read_json_body(self) -> dict:
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        data = json.loads(raw.decode("utf-8"))
        if not isinstance(data, dict):
            raise ValueError("JSON body must be an object.")
        return data

    def do_OPTIONS(self):
        self.send_response(204)
        self._send_cors_headers()
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _method_not_allowed(self):
        self._send_json(405, {"success": False, "error": f"Method {self.command} is not allowed on this endpoint."})

    def do_PUT(self):
        self._method_not_allowed()

    def do_PATCH(self):
        self._method_not_allowed()

    def do_DELETE(self):
        self._method_not_allowed()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        route = self._normalize_route(self.path)
        lower_route = route.lower()

        try:
            # 0. Health / Readiness Endpoint (exposes only safe operational status)
            if route in ("/api/health", "/api"):
                records = load_db()
                mode = get_storage_mode()
                self._send_json(
                    200,
                    {
                        "success": True,
                        "status": "ok",
                        "service": "aufbruch-2026-api",
                        "storageMode": mode,
                        "durableStorageConfigured": mode != "tmp-ephemeral",
                        "recordCount": len(records),
                    },
                )
                return

            # 1. Check Admin Session Status
            if route == "/api/admin/session":
                sess = get_valid_session(self)
                if not sess:
                    self._send_json(401, {"success": False, "authenticated": False, "error": "Unauthorized"})
                    return
                self._send_json(200, {"success": True, "authenticated": True, "username": sess["username"]})
                return

            # 2. Protected Admin Dashboard Data Endpoint
            if route == "/api/admin/dashboard":
                sess = get_valid_session(self)
                if not sess:
                    self._send_json(
                        401,
                        {
                            "success": False,
                            "authenticated": False,
                            "error": "Unauthorized access. Please log in with valid administrator credentials.",
                        },
                    )
                    return
                self._send_json(200, build_dashboard_payload())
                return

            # 2B. Public Student Master List for Registration Dropdown
            if route == "/api/students":
                qs = urllib.parse.parse_qs(parsed.query)
                batch_filter = (qs.get("batchYear", [""])[0] or "").strip()
                students = load_students_db()
                records = load_db()
                registered_map: dict[str, dict] = {}
                for r in records:
                    by = str(r.get("batchYear", "")).strip()
                    stu_id = str(r.get("studentId") or "").strip()
                    reg_info = {
                        "registrationId": r.get("registrationId"),
                        "ticketId": r.get("ticketId"),
                        "name": r.get("name"),
                        "studentId": stu_id,
                    }
                    if stu_id:
                        registered_map[f"STU::{stu_id}"] = reg_info
                    for nm in (r.get("originalExcelName"), r.get("name")):
                        clean_nm = re.sub(r"\s+", " ", str(nm or "").strip()).upper()
                        if by and clean_nm:
                            registered_map[f"{by}::{clean_nm}"] = reg_info
                if batch_filter:
                    filtered_students = [
                        s for s in students if str(s.get("batchYear", "")).strip() == batch_filter
                    ]
                else:
                    filtered_students = students
                self._send_json(
                    200,
                    {
                        "success": True,
                        "batchYears": BATCH_YEARS,
                        "officialBatchTotals": OFFICIAL_BATCH_TOTALS,
                        "officialOverallTotal": OFFICIAL_OVERALL_TOTAL,
                        "students": filtered_students,
                        "registeredMap": registered_map,
                    },
                )
                return

            # 2C. Public Ticket Lookup & SVG QR Code Endpoints
            if route == "/api/ticket":
                qs = urllib.parse.parse_qs(parsed.query)
                q_token = (qs.get("token", [""])[0] or "").strip()
                q_id = (qs.get("id", [""])[0] or "").strip()
                records = load_db()
                found = None
                for r in records:
                    if q_token and str(r.get("ticketToken", "")).strip().upper() == q_token.upper():
                        found = r
                        break
                    if q_id and (
                        str(r.get("registrationId", "")).strip() == normalize_reg_id(q_id)
                        or str(r.get("ticketId", "")).strip().upper() == q_id.upper()
                    ):
                        found = r
                        break
                if not found:
                    self._send_json(404, {"success": False, "error": "Ticket not found."})
                    return
                self._send_json(200, {"success": True, "ticket": found})
                return

            if route == "/api/ticket/qr.svg":
                qs = urllib.parse.parse_qs(parsed.query)
                q_token = (qs.get("token", [""])[0] or "AUFBRUCH-2026").strip()
                svg_bytes = make_qr_svg(q_token).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "image/svg+xml; charset=utf-8")
                self.send_header("Content-Length", str(len(svg_bytes)))
                self.send_header("Cache-Control", "public, max-age=3600")
                self._send_cors_headers()
                self.end_headers()
                self.wfile.write(svg_bytes)
                return

            # 2D. Protected Admin Check-in Excel (.xlsx) Export
            if route == "/api/admin/checkin/export-xlsx":
                sess = get_valid_session(self)
                if not sess:
                    self._send_json(401, {"success": False, "error": "Unauthorized access."})
                    return
                records = load_db()
                xlsx_bytes = build_checkin_xlsx_bytes(records)
                self.send_response(200)
                self.send_header(
                    "Content-Type",
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
                self.send_header(
                    "Content-Disposition",
                    'attachment; filename="Aufbruch_2026_Checkin_Report.xlsx"',
                )
                self.send_header("Content-Length", str(len(xlsx_bytes)))
                self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
                self._send_cors_headers()
                self.end_headers()
                self.wfile.write(xlsx_bytes)
                return

            if route == "/api/admin/whatsapp-config":
                sess = get_valid_session(self)
                if not sess:
                    self._send_json(401, {"success": False, "error": "Unauthorized access."})
                    return
                self._send_json(200, {"success": True, **get_whatsapp_cloud_api_status()})
                return

            # Any other /api/ GET route returns JSON 404 (never HTML)
            if route.startswith("/api/"):
                self._send_json(404, {"success": False, "error": "API endpoint not found."})
                return

            # 3. Static File Serving strictly from public/ & Clean SPA Routing
            if lower_route in (
                "/",
                "/index.html",
                "/register",
                "/dashboard",
                "/admin",
                "/admin/login",
                "/scanner",
                "/checkin",
            ):
                file_path = _resolve_index_html()
            else:
                rel = parsed.path.lstrip("/")
                public_root = PUBLIC_DIR.resolve()
                file_path = (PUBLIC_DIR / rel).resolve()
                if not str(file_path).startswith(str(public_root)):
                    self.send_error(403, "Forbidden")
                    return

            if not file_path.exists() or not file_path.is_file():
                self.send_error(404, "Not Found")
                return

            mime_type, _ = mimetypes.guess_type(str(file_path))
            if file_path.suffix.lower() == ".ttf":
                mime_type = "font/ttf"
            elif not mime_type:
                mime_type = "application/octet-stream"

            data = file_path.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", mime_type)
            self.send_header("Content-Length", str(len(data)))
            if file_path.suffix.lower() == ".html":
                self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
            self.end_headers()
            self.wfile.write(data)
        except Exception as exc:
            if route.startswith("/api/"):
                self._send_json(500, {"success": False, "error": f"Internal server error: {exc}"})
            else:
                self.send_error(500, "Internal Server Error")

    def do_POST(self):
        route = self._normalize_route(self.path)
        try:
            body = self._read_json_body()
        except Exception:
            self._send_json(400, {"success": False, "error": "Invalid JSON request payload."})
            return

        try:
            self._handle_post_route(route, body)
        except Exception as exc:
            self._send_json(500, {"success": False, "error": f"Internal server error: {exc}"})

    def _handle_post_route(self, route: str, body: dict):

        # 1. Admin Login Route
        if route == "/api/admin/login":
            username = str(body.get("username", "")).strip()
            password = str(body.get("password", ""))
            if not verify_admin_credentials(username, password):
                self._send_json(
                    401,
                    {
                        "success": False,
                        "authenticated": False,
                        "error": "Invalid administrator username or password.",
                    },
                )
                return

            token = create_session(username)
            cookie_val = self._build_session_cookie(token, SESSION_TTL_SECONDS)
            self._send_json(
                200,
                {
                    "success": True,
                    "authenticated": True,
                    "username": username,
                    "sessionToken": token,
                },
                extra_headers=[("Set-Cookie", cookie_val)],
            )
            return

        # 2. Admin Logout Route
        if route == "/api/admin/logout":
            sess = get_valid_session(self)
            if sess and sess.get("token"):
                revoke_session(sess["token"])
            auth_header = self.headers.get("Authorization", "")
            if auth_header.startswith("Bearer "):
                revoke_session(auth_header[7:].strip())
            clear_cookie = self._build_session_cookie("", 0)
            self._send_json(
                200,
                {"success": True, "authenticated": False},
                extra_headers=[("Set-Cookie", clear_cookie)],
            )
            return

        # 3. Protected Admin Seed Route
        if route == "/api/admin/seed":
            sess = get_valid_session(self)
            if not sess:
                self._send_json(401, {"success": False, "error": "Unauthorized"})
                return
            seeded = [enrich_registration(r) for r in DEFAULT_SEED_DATA]
            save_db(seeded)
            self._send_json(200, build_dashboard_payload())
            return

        # 4. Protected Admin Update Registration Route
        if route == "/api/admin/update":
            sess = get_valid_session(self)
            if not sess:
                self._send_json(
                    401,
                    {
                        "success": False,
                        "error": "Unauthorized access. Valid administrator session required.",
                    },
                )
                return

            reg_id = str(body.get("registrationId", "")).strip()
            name = str(body.get("name", "")).strip()
            place = str(body.get("place", "")).strip()
            batch_year = str(body.get("batchYear", "")).strip()
            whatsapp_number = str(body.get("whatsappNumber", "")).strip()
            participation = str(body.get("participation", "")).strip()

            if not reg_id:
                self._send_json(400, {"success": False, "error": "Registration ID is required."})
                return
            if len(name) < 2:
                self._send_json(400, {"success": False, "error": "Please enter a valid full name (minimum 2 characters)."})
                return
            if len(place) < 2:
                self._send_json(400, {"success": False, "error": "Please enter a valid locality / place."})
                return
            if not re.match(r"^(19[5-9]\d|20[0-2]\d)(\s*[-–/]\s*(19[5-9]\d|20[0-2]\d|\d{2}))?$", batch_year):
                self._send_json(400, {"success": False, "error": "Please enter a valid 4-digit Batch Year (e.g., 2018)."})
                return

            phone_res = normalize_indian_phone(whatsapp_number)
            if not phone_res["isValid"]:
                self._send_json(400, {"success": False, "error": "Please enter a valid 10-digit mobile number."})
                return

            if participation not in ("പങ്കെടുക്കും", "സാധിക്കില്ല"):
                self._send_json(
                    400,
                    {"success": False, "error": "Please select a valid Attendance Status (പങ്കെടുക്കും or സാധിക്കില്ല)."},
                )
                return

            records = load_db()
            found_index = -1
            for idx, r in enumerate(records):
                if str(r.get("registrationId", "")).strip() == reg_id:
                    found_index = idx
                    break

            if found_index == -1:
                self._send_json(404, {"success": False, "error": f"Registration '{reg_id}' not found."})
                return

            existing_rec = records[found_index]
            existing_ts = existing_rec.get("timestamp") or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            updated_rec = enrich_registration(
                {
                    "registrationId": reg_id,
                    "ticketId": existing_rec.get("ticketId"),
                    "ticketToken": existing_rec.get("ticketToken"),
                    "timestamp": existing_ts,
                    "name": name,
                    "originalExcelName": body.get("originalExcelName") or existing_rec.get("originalExcelName") or name,
                    "nameEdited": existing_rec.get("nameEdited", False),
                    "studentId": existing_rec.get("studentId", ""),
                    "place": place,
                    "batchYear": batch_year,
                    "whatsappNumber": whatsapp_number,
                    "participation": participation,
                    "whatsappSent": existing_rec.get("whatsappSent", False),
                    "whatsappSentAt": existing_rec.get("whatsappSentAt", ""),
                    "whatsappSentCount": existing_rec.get("whatsappSentCount", 0),
                    "whatsappCloudApiMessageId": existing_rec.get("whatsappCloudApiMessageId", ""),
                    "checkedIn": existing_rec.get("checkedIn", False),
                    "checkInTimestamp": existing_rec.get("checkInTimestamp", ""),
                    "checkedInBy": existing_rec.get("checkedInBy", ""),
                }
            )
            records[found_index] = updated_rec
            save_db(records)

            payload = build_dashboard_payload()
            payload["updatedRecord"] = updated_rec
            payload["message"] = f"Registration #{reg_id} updated successfully."
            self._send_json(200, payload)
            return

        # 4B. Protected Admin Update WhatsApp Message Sent Status Route
        if route == "/api/admin/whatsapp-status":
            sess = get_valid_session(self)
            if not sess:
                self._send_json(
                    401,
                    {
                        "success": False,
                        "error": "Unauthorized access. Valid administrator session required.",
                    },
                )
                return

            reg_id = str(body.get("registrationId", "")).strip()
            if not reg_id:
                self._send_json(400, {"success": False, "error": "Registration ID is required."})
                return

            wa_sent = bool(body.get("whatsappSent", True))
            records = load_db()
            found_index = -1
            for idx, r in enumerate(records):
                if str(r.get("registrationId", "")).strip() == reg_id:
                    found_index = idx
                    break

            if found_index == -1:
                self._send_json(404, {"success": False, "error": f"Registration '{reg_id}' not found."})
                return

            existing_rec = dict(records[found_index])
            prev_count = int(existing_rec.get("whatsappSentCount") or 0)
            existing_rec["whatsappSent"] = wa_sent
            if wa_sent:
                existing_rec["whatsappSentAt"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                existing_rec["whatsappSentCount"] = prev_count + 1
            else:
                existing_rec["whatsappSentAt"] = ""
                existing_rec["whatsappSentCount"] = 0

            updated_rec = enrich_registration(existing_rec)
            records[found_index] = updated_rec
            save_db(records)

            payload = build_dashboard_payload()
            payload["updatedRecord"] = updated_rec
            payload["message"] = f"WhatsApp message status saved for registration #{reg_id}."
            self._send_json(200, payload)
            return

        # 4C. Protected Admin WhatsApp Business Cloud API Send Route (Sender 8606140996)
        if route == "/api/admin/whatsapp-send-api":
            sess = get_valid_session(self)
            if not sess:
                self._send_json(401, {"success": False, "error": "Unauthorized access."})
                return

            reg_id = str(body.get("registrationId", "")).strip()
            custom_msg = str(body.get("message", "")).strip()
            records = load_db()
            found_index = -1
            for idx, r in enumerate(records):
                if str(r.get("registrationId", "")).strip() == reg_id:
                    found_index = idx
                    break
            if found_index == -1:
                self._send_json(404, {"success": False, "error": f"Registration '{reg_id}' not found."})
                return

            target_rec = dict(records[found_index])
            msg_to_send = custom_msg or target_rec.get("whatsAppMessage") or build_whatsapp_message(target_rec.get("name", ""))
            wa_num = str(target_rec.get("waNumber") or "").strip()
            if not wa_num:
                self._send_json(400, {"success": False, "error": "Recipient does not have a valid WhatsApp number."})
                return

            api_res = send_whatsapp_cloud_api_message(wa_num, msg_to_send)
            if not api_res.get("sent"):
                self._send_json(
                    400 if not api_res.get("configured") else 502,
                    {
                        "success": False,
                        "cloudApi": api_res,
                        "message": api_res.get("error") or "WhatsApp Cloud API message could not be sent.",
                        "error": api_res.get("error") or "WhatsApp Cloud API message could not be sent.",
                    },
                )
                return

            prev_count = int(target_rec.get("whatsappSentCount") or 0)
            target_rec["whatsappSent"] = True
            target_rec["whatsappSentAt"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            target_rec["whatsappSentCount"] = prev_count + 1
            target_rec["whatsappCloudApiMessageId"] = api_res.get("messageId", "")
            updated_rec = enrich_registration(target_rec)
            records[found_index] = updated_rec
            save_db(records)

            payload = build_dashboard_payload()
            payload["updatedRecord"] = updated_rec
            payload["cloudApi"] = api_res
            payload["message"] = f"WhatsApp message sent via Cloud API from {WHATSAPP_SENDER_NUMBER} (ID: {api_res.get('messageId')})."
            self._send_json(200, payload)
            return

        # 4D. Protected Admin QR Ticket Verification Route
        if route == "/api/admin/checkin/verify":
            sess = get_valid_session(self)
            if not sess:
                self._send_json(401, {"success": False, "error": "Unauthorized access. Valid administrator session required."})
                return

            raw_qr = str(body.get("qrData") or body.get("ticketToken") or "").strip()
            allow_id_lookup = bool(body.get("allowIdLookup", False))
            if not raw_qr:
                self._send_json(
                    200,
                    {
                        "success": False,
                        "valid": False,
                        "status": "INVALID",
                        "headline": "INVALID TICKET – PLEASE VERIFY",
                        "message": "INVALID TICKET – PLEASE VERIFY",
                    },
                )
                return

            # Extract token if QR contains JSON or URL
            candidate_token = raw_qr
            if raw_qr.startswith("{") and raw_qr.endswith("}"):
                try:
                    parsed_qr = json.loads(raw_qr)
                    if isinstance(parsed_qr, dict):
                        candidate_token = str(parsed_qr.get("ticketToken") or parsed_qr.get("token") or raw_qr).strip()
                except Exception:
                    pass
            elif "token=" in raw_qr:
                try:
                    qs = urllib.parse.parse_qs(urllib.parse.urlparse(raw_qr).query)
                    if qs.get("token"):
                        candidate_token = qs["token"][0].strip()
                except Exception:
                    pass

            m_tok = re.search(r"(AUF26-ANWAR\d{3,}-[A-F0-9]{12})", candidate_token, re.I)
            if m_tok:
                candidate_token = m_tok.group(1).upper()

            records = load_db()
            found_rec = None
            for r in records:
                if str(r.get("ticketToken", "")).strip().upper() == candidate_token.upper():
                    found_rec = r
                    break
                if allow_id_lookup and (
                    str(r.get("ticketId", "")).strip().upper() == candidate_token.upper()
                    or (candidate_token.isdigit() and str(r.get("registrationId", "")).strip() == normalize_reg_id(candidate_token))
                ):
                    found_rec = r
                    break

            if not found_rec:
                self._send_json(
                    200,
                    {
                        "success": False,
                        "valid": False,
                        "status": "INVALID",
                        "headline": "INVALID TICKET – PLEASE VERIFY",
                        "message": "INVALID TICKET – PLEASE VERIFY",
                    },
                )
                return

            if found_rec.get("checkedIn"):
                self._send_json(
                    200,
                    {
                        "success": True,
                        "valid": True,
                        "alreadyCheckedIn": True,
                        "status": "ALREADY_CONFIRMED",
                        "headline": "ALREADY CONFIRMED – ENTRY COMPLETED",
                        "message": "ALREADY CONFIRMED – ENTRY COMPLETED",
                        "checkInTimestamp": found_rec.get("checkInTimestamp", ""),
                        "checkedInBy": found_rec.get("checkedInBy", ""),
                        "participant": found_rec,
                    },
                )
                return

            self._send_json(
                200,
                {
                    "success": True,
                    "valid": True,
                    "alreadyCheckedIn": False,
                    "status": "VALID_PENDING",
                    "headline": "< TICKET CONFIRMED >",
                    "message": "Valid registration ticket verified. Ready for check-in confirmation.",
                    "participant": found_rec,
                },
            )
            return

        # 4E. Protected Admin One-Time Check-in Confirmation Route
        if route == "/api/admin/checkin/confirm":
            sess = get_valid_session(self)
            if not sess:
                self._send_json(401, {"success": False, "error": "Unauthorized access. Valid administrator session required."})
                return

            target_token = str(body.get("ticketToken") or "").strip()
            target_reg_id = str(body.get("registrationId") or "").strip()
            if not target_token and not target_reg_id:
                self._send_json(
                    400,
                    {
                        "success": False,
                        "status": "INVALID",
                        "headline": "INVALID TICKET – PLEASE VERIFY",
                        "message": "INVALID TICKET – PLEASE VERIFY",
                    },
                )
                return

            records = load_db()
            found_index = -1
            for idx, r in enumerate(records):
                if target_token and str(r.get("ticketToken", "")).strip().upper() == target_token.upper():
                    found_index = idx
                    break
                if not target_token and target_reg_id and str(r.get("registrationId", "")).strip() == normalize_reg_id(target_reg_id):
                    found_index = idx
                    break

            if found_index == -1:
                self._send_json(
                    404,
                    {
                        "success": False,
                        "valid": False,
                        "status": "INVALID",
                        "headline": "INVALID TICKET – PLEASE VERIFY",
                        "message": "INVALID TICKET – PLEASE VERIFY",
                    },
                )
                return

            existing_rec = dict(records[found_index])
            if existing_rec.get("checkedIn"):
                self._send_json(
                    409,
                    {
                        "success": False,
                        "valid": True,
                        "alreadyCheckedIn": True,
                        "status": "ALREADY_CONFIRMED",
                        "headline": "ALREADY CONFIRMED – ENTRY COMPLETED",
                        "message": "ALREADY CONFIRMED – ENTRY COMPLETED",
                        "checkInTimestamp": existing_rec.get("checkInTimestamp", ""),
                        "checkedInBy": existing_rec.get("checkedInBy", ""),
                        "participant": existing_rec,
                    },
                )
                return

            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            existing_rec["checkedIn"] = True
            existing_rec["checkInStatus"] = "CHECKED IN"
            existing_rec["checkInTimestamp"] = now_str
            existing_rec["checkedInBy"] = sess.get("username", "admin")
            updated_rec = enrich_registration(existing_rec)
            records[found_index] = updated_rec
            save_db(records)

            dash_payload = build_dashboard_payload()
            self._send_json(
                200,
                {
                    "success": True,
                    "valid": True,
                    "alreadyCheckedIn": False,
                    "status": "CONFIRMED_NOW",
                    "headline": "TICKET CONFIRMED SUCCESSFULLY",
                    "message": "TICKET CONFIRMED SUCCESSFULLY",
                    "checkInTimestamp": updated_rec["checkInTimestamp"],
                    "checkedInBy": updated_rec["checkedInBy"],
                    "participant": updated_rec,
                    "dashboard": dash_payload,
                },
            )
            return

        # 4F. Protected Admin Student Master List CRUD & Excel Import Routes
        if route == "/api/admin/students/add":
            sess = get_valid_session(self)
            if not sess:
                self._send_json(401, {"success": False, "error": "Unauthorized access."})
                return
            batch_year = str(body.get("batchYear", "")).strip()
            name = re.sub(r"\s+", " ", str(body.get("name", "")).strip()).upper()
            serial_raw = body.get("serialNo")
            if batch_year not in BATCH_YEARS:
                self._send_json(400, {"success": False, "error": "Please select a valid Batch Year (2001–2026)."})
                return
            if len(name) < 2:
                self._send_json(400, {"success": False, "error": "Please enter a valid student name."})
                return
            students = load_students_db()
            for st in students:
                if str(st.get("batchYear", "")).strip() == batch_year and str(st.get("name", "")).strip().upper() == name:
                    self._send_json(409, {"success": False, "error": f"'{name}' already exists in Batch {batch_year}."})
                    return
            sl_num = None
            if serial_raw is not None and str(serial_raw).strip() != "":
                try:
                    sl_num = int(float(str(serial_raw).strip()))
                except Exception:
                    sl_num = None
            if sl_num is None:
                existing_sls = [int(s["serialNo"]) for s in students if isinstance(s.get("serialNo"), int)]
                sl_num = (max(existing_sls) if existing_sls else len(students)) + 1
            stu_id = f"STU-{batch_year}-{sl_num:03d}-{secrets.token_hex(2).upper()}"
            new_st = {
                "studentId": stu_id,
                "serialNo": sl_num,
                "batchYear": batch_year,
                "name": name,
            }
            students.append(new_st)
            students.sort(key=lambda x: (str(x.get("batchYear", "")), int(x.get("serialNo") or 9999), str(x.get("name", ""))))
            save_students_db(students)
            payload = build_dashboard_payload()
            payload["addedStudent"] = new_st
            payload["message"] = f"Added {name} to Batch {batch_year}."
            self._send_json(200, payload)
            return

        if route == "/api/admin/students/update":
            sess = get_valid_session(self)
            if not sess:
                self._send_json(401, {"success": False, "error": "Unauthorized access."})
                return
            student_id = str(body.get("studentId", "")).strip()
            batch_year = str(body.get("batchYear", "")).strip()
            name = re.sub(r"\s+", " ", str(body.get("name", "")).strip()).upper()
            serial_raw = body.get("serialNo")
            if not student_id:
                self._send_json(400, {"success": False, "error": "studentId is required."})
                return
            if batch_year not in BATCH_YEARS:
                self._send_json(400, {"success": False, "error": "Please select a valid Batch Year (2001–2026)."})
                return
            if len(name) < 2:
                self._send_json(400, {"success": False, "error": "Please enter a valid student name."})
                return
            students = load_students_db()
            found_idx = -1
            for idx, st in enumerate(students):
                if str(st.get("studentId", "")).strip() == student_id:
                    found_idx = idx
                    break
            if found_idx == -1:
                self._send_json(404, {"success": False, "error": "Student record not found."})
                return
            sl_num = students[found_idx].get("serialNo")
            if serial_raw is not None and str(serial_raw).strip() != "":
                try:
                    sl_num = int(float(str(serial_raw).strip()))
                except Exception:
                    pass
            students[found_idx] = {
                "studentId": student_id,
                "serialNo": sl_num,
                "batchYear": batch_year,
                "name": name,
            }
            save_students_db(students)
            payload = build_dashboard_payload()
            payload["updatedStudent"] = students[found_idx]
            payload["message"] = f"Updated student record {name} (Batch {batch_year})."
            self._send_json(200, payload)
            return

        if route == "/api/admin/students/delete":
            sess = get_valid_session(self)
            if not sess:
                self._send_json(401, {"success": False, "error": "Unauthorized access."})
                return
            student_id = str(body.get("studentId", "")).strip()
            if not student_id:
                self._send_json(400, {"success": False, "error": "studentId is required."})
                return
            students = load_students_db()
            new_students = [st for st in students if str(st.get("studentId", "")).strip() != student_id]
            if len(new_students) == len(students):
                self._send_json(404, {"success": False, "error": "Student record not found."})
                return
            save_students_db(new_students)
            payload = build_dashboard_payload()
            payload["deletedStudentId"] = student_id
            payload["message"] = "Student record removed from master list."
            self._send_json(200, payload)
            return

        if route == "/api/admin/students/import":
            sess = get_valid_session(self)
            if not sess:
                self._send_json(401, {"success": False, "error": "Unauthorized access."})
                return
            b64_data = str(body.get("fileBase64", "")).strip()
            mode = str(body.get("mode", "merge")).strip().lower()
            if not b64_data:
                self._send_json(400, {"success": False, "error": "Excel file content (fileBase64) is required."})
                return
            if "," in b64_data:
                b64_data = b64_data.split(",", 1)[1]
            try:
                raw_bytes = base64.b64decode(b64_data)
                imported_students, removed_dups = parse_alumni_xlsx_bytes(raw_bytes)
            except Exception as exc:
                self._send_json(400, {"success": False, "error": f"Failed to parse Excel (.xlsx) file: {exc}"})
                return
            if not imported_students:
                self._send_json(400, {"success": False, "error": "No valid batch/student rows found in uploaded Excel file."})
                return
            if mode == "replace":
                final_students = imported_students
            else:
                existing_students = load_students_db()
                seen = {
                    (str(s.get("batchYear", "")).strip(), str(s.get("name", "")).strip().upper())
                    for s in existing_students
                }
                final_students = list(existing_students)
                for st in imported_students:
                    k = (st["batchYear"], st["name"].upper())
                    if k not in seen:
                        seen.add(k)
                        final_students.append(st)
                final_students.sort(key=lambda x: (str(x.get("batchYear", "")), int(x.get("serialNo") or 9999), str(x.get("name", ""))))
            save_students_db(final_students)
            payload = build_dashboard_payload()
            payload["importedCount"] = len(imported_students)
            payload["removedDuplicates"] = removed_dups
            payload["message"] = f"Successfully imported {len(imported_students)} student records from Excel."
            self._send_json(200, payload)
            return

        # 5. Protected Admin Delete Registration Route
        if route == "/api/admin/delete":
            sess = get_valid_session(self)
            if not sess:
                self._send_json(
                    401,
                    {
                        "success": False,
                        "error": "Unauthorized access. Valid administrator session required.",
                    },
                )
                return

            reg_id = str(body.get("registrationId", "")).strip()
            if not reg_id:
                self._send_json(400, {"success": False, "error": "Registration ID is required."})
                return

            records = load_db()
            new_records = [r for r in records if str(r.get("registrationId", "")).strip() != reg_id]

            if len(new_records) == len(records):
                self._send_json(404, {"success": False, "error": f"Registration '{reg_id}' not found."})
                return

            save_db(new_records)

            payload = build_dashboard_payload()
            payload["deletedId"] = reg_id
            payload["message"] = f"Registration #{reg_id} deleted permanently."
            self._send_json(200, payload)
            return

        # 6. Public Registration Submission Route
        if route == "/api/register":
            name = re.sub(r"\s+", " ", str(body.get("name", "")).strip())
            orig_excel_name = re.sub(r"\s+", " ", str(body.get("originalExcelName") or name).strip())
            student_id = str(body.get("studentId") or "").strip()
            name_edited = bool(body.get("nameEdited") or (orig_excel_name and orig_excel_name.upper() != name.upper()))
            place = str(body.get("place", "")).strip()
            batch_year = str(body.get("batchYear", "")).strip()
            whatsapp_number = str(body.get("whatsappNumber", "")).strip()
            participation = str(body.get("participation", "")).strip()

            if not re.match(r"^(19[5-9]\d|20[0-2]\d)(\s*[-–/]\s*(19[5-9]\d|20[0-2]\d|\d{2}))?$", batch_year):
                self._send_json(400, {"success": False, "error": "Please select a valid Batch Year (2001–2026)."})
                return
            if len(name) < 2:
                self._send_json(400, {"success": False, "error": "Please select or enter your full name."})
                return
            if len(place) < 2:
                self._send_json(400, {"success": False, "error": "Please enter your place."})
                return

            phone_res = normalize_indian_phone(whatsapp_number)
            if not phone_res["isValid"]:
                self._send_json(400, {"success": False, "error": phone_res["error"]})
                return

            if participation not in ("പങ്കെടുക്കും", "സാധിക്കില്ല"):
                self._send_json(400, {"success": False, "error": "Please select a valid participation option."})
                return

            records = load_db()

            # Prevent duplicate student registration in the same Batch Year
            now_dt = datetime.now()
            norm_name_up = name.upper()
            norm_orig_up = orig_excel_name.upper()
            for existing in records:
                ex_batch = str(existing.get("batchYear", "")).strip()
                if ex_batch != batch_year:
                    continue
                ex_name_up = re.sub(r"\s+", " ", str(existing.get("name", "")).strip()).upper()
                ex_orig_up = re.sub(r"\s+", " ", str(existing.get("originalExcelName") or ex_name_up).strip()).upper()
                ex_stu_id = str(existing.get("studentId") or "").strip()
                if (
                    (student_id and ex_stu_id and student_id == ex_stu_id)
                    or norm_name_up in (ex_name_up, ex_orig_up)
                    or norm_orig_up in (ex_name_up, ex_orig_up)
                ):
                    ex_ticket = existing.get("ticketId") or format_anwar_id(existing.get("registrationId", "001"))
                    self._send_json(
                        409,
                        {
                            "success": False,
                            "duplicate": True,
                            "existingTicketId": ex_ticket,
                            "message": f"Duplicate registration: {name} (Batch {batch_year}) is already registered under ID {ex_ticket}.",
                            "error": f"Duplicate registration: {name} (Batch {batch_year}) is already registered under ID {ex_ticket}.",
                        },
                    )
                    return

            numeric_ids = [
                int(str(r.get("registrationId", "")))
                for r in records
                if str(r.get("registrationId", "")).isdigit()
            ]
            next_num = (max(numeric_ids) if numeric_ids else len(records)) + 1
            reg_id = f"{next_num:03d}"

            new_rec = enrich_registration(
                {
                    "registrationId": reg_id,
                    "timestamp": now_dt.strftime("%Y-%m-%d %H:%M:%S"),
                    "name": name,
                    "originalExcelName": orig_excel_name,
                    "nameEdited": name_edited,
                    "studentId": student_id,
                    "place": place,
                    "batchYear": batch_year,
                    "whatsappNumber": whatsapp_number,
                    "participation": participation,
                }
            )

            # Optional automated WhatsApp Cloud API send from 8606140996 if credentials are set
            cloud_api_res = {"configured": False, "sent": False}
            if new_rec["shouldSendWhatsApp"] and get_whatsapp_cloud_api_status()["configured"]:
                cloud_api_res = send_whatsapp_cloud_api_message(new_rec["waNumber"], new_rec["whatsAppMessage"])
                if cloud_api_res.get("sent"):
                    new_rec["whatsappSent"] = True
                    new_rec["whatsappSentAt"] = now_dt.strftime("%Y-%m-%d %H:%M:%S")
                    new_rec["whatsappSentCount"] = 1
                    new_rec["whatsappCloudApiMessageId"] = cloud_api_res.get("messageId", "")

            records.insert(0, new_rec)
            save_db(records)
            gas_synced = _sync_registration_to_gas(new_rec)

            self._send_json(
                200,
                {
                    "success": True,
                    "message": "Registration completed successfully",
                    "data": dict(new_rec),
                    "gasSynced": gas_synced,
                    "whatsappCloudApi": cloud_api_res,
                    "storageMode": get_storage_mode(),
                    "registrationId": new_rec["registrationId"],
                    "ticketId": new_rec["ticketId"],
                    "ticketToken": new_rec["ticketToken"],
                    "qrMatrix": new_rec["qrMatrix"],
                    "confirmationMessage": EXACT_CONFIRMATION_MESSAGE,
                    "name": new_rec["name"],
                    "originalExcelName": new_rec["originalExcelName"],
                    "nameEdited": new_rec["nameEdited"],
                    "place": new_rec["place"],
                    "batchYear": new_rec["batchYear"],
                    "formattedPhone": new_rec["formattedPhone"],
                    "participation": new_rec["participation"],
                    "shouldSendWhatsApp": new_rec["shouldSendWhatsApp"],
                    "whatsAppMessage": new_rec["whatsAppMessage"],
                    "whatsAppClickToChatUrl": new_rec["whatsAppClickToChatUrl"],
                },
            )
            return

        self._send_json(404, {"success": False, "error": "Endpoint not found."})


class DualStackHTTPServer(ThreadingHTTPServer):
    address_family = socket.AF_INET6

    def server_bind(self):
        try:
            self.socket.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
        except Exception:
            pass
        return super().server_bind()


def run_server(port: int | None = None):
    if port is None:
        port = int(os.environ.get("PORT", "8765"))
    load_db()
    try:
        server = DualStackHTTPServer(("::", port), AufbruchRequestHandler)
    except OSError:
        server = ThreadingHTTPServer(("0.0.0.0", port), AufbruchRequestHandler)
    print(f"Aufbruch 2026 Secure Server listening on http://localhost:{port}")
    server.serve_forever()


if __name__ == "__main__":
    run_server()
