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
KV_RECORDS_KEY = os.environ.get("KV_RECORDS_KEY", "aufbruch:registrations_v1")
BLOB_RECORDS_PATH = os.environ.get("BLOB_RECORDS_PATH", "aufbruch/registrations_v1.json")
BLOB_REVOKED_PATH = os.environ.get("BLOB_REVOKED_PATH", "aufbruch/revoked_sessions_v1.json")


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


DB_FILE = _resolve_db_file()

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


def enrich_registration(rec: dict) -> dict:
    phone_data = normalize_indian_phone(rec.get("whatsappNumber", ""))
    participation = str(rec.get("participation", "")).strip()
    is_participating = participation == "പങ്കെടുക്കും"
    should_send = bool(is_participating and phone_data["isValid"])
    msg = build_whatsapp_message(rec.get("name", "")) if should_send else ""
    wa_url = (
        f"https://wa.me/{phone_data['waNumber']}?text={urllib.parse.quote(msg, safe='')}"
        if should_send
        else ""
    )

    place_str = str(rec.get("place", "")).strip().title()
    raw_id = str(rec.get("registrationId") or "001").replace("AUF-2026-0", "").replace("AUF-2026-", "")
    return {
        "registrationId": raw_id,
        "timestamp": rec.get("timestamp") or datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "name": str(rec.get("name", "")).strip(),
        "place": place_str,
        "batchYear": str(rec.get("batchYear", "")).strip(),
        "whatsappNumber": str(rec.get("whatsappNumber", "")).strip(),
        "formattedPhone": phone_data["display"] if phone_data["isValid"] else str(rec.get("whatsappNumber", "")),
        "waNumber": phone_data["waNumber"] if phone_data["isValid"] else "",
        "participation": participation,
        "shouldSendWhatsApp": should_send,
        "whatsAppMessage": msg,
        "whatsAppClickToChatUrl": wa_url,
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


def build_dashboard_payload() -> dict:
    records = load_db()
    total = len(records)
    participating = sum(1 for r in records if r["participation"] == "പങ്കെടുക്കും")
    not_participating = total - participating
    rate = round((participating / total) * 100, 1) if total > 0 else 0

    batch_map: dict[str, dict] = {}
    place_map: dict[str, dict] = {}
    for r in records:
        is_yes = r["participation"] == "പങ്കെടുക്കും"
        b_key = r["batchYear"] or "Unspecified"
        if b_key not in batch_map:
            batch_map[b_key] = {"batchYear": b_key, "total": 0, "yes": 0, "no": 0}
        batch_map[b_key]["total"] += 1
        if is_yes:
            batch_map[b_key]["yes"] += 1
        else:
            batch_map[b_key]["no"] += 1

        p_key = r["place"] or "Unspecified"
        if p_key not in place_map:
            place_map[p_key] = {"place": p_key, "total": 0, "yes": 0, "no": 0}
        place_map[p_key]["total"] += 1
        if is_yes:
            place_map[p_key]["yes"] += 1
        else:
            place_map[p_key]["no"] += 1

    return {
        "success": True,
        "authenticated": True,
        "registrations": records,
        "stats": {
            "total": total,
            "participating": participating,
            "notParticipating": not_participating,
            "confirmationRate": rate,
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

            # Any other /api/ GET route returns JSON 404 (never HTML)
            if route.startswith("/api/"):
                self._send_json(404, {"success": False, "error": "API endpoint not found."})
                return

            # 3. Static File Serving strictly from public/ & Clean SPA Routing
            if lower_route in ("/", "/index.html", "/register", "/dashboard", "/admin", "/admin/login"):
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

            existing_ts = records[found_index].get("timestamp") or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            updated_rec = enrich_registration(
                {
                    "registrationId": reg_id,
                    "timestamp": existing_ts,
                    "name": name,
                    "place": place,
                    "batchYear": batch_year,
                    "whatsappNumber": whatsapp_number,
                    "participation": participation,
                }
            )
            records[found_index] = updated_rec
            save_db(records)

            payload = build_dashboard_payload()
            payload["updatedRecord"] = updated_rec
            payload["message"] = f"Registration #{reg_id} updated successfully."
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
            name = str(body.get("name", "")).strip()
            place = str(body.get("place", "")).strip()
            batch_year = str(body.get("batchYear", "")).strip()
            whatsapp_number = str(body.get("whatsappNumber", "")).strip()
            participation = str(body.get("participation", "")).strip()

            if len(name) < 2:
                self._send_json(400, {"success": False, "error": "Please enter your full name."})
                return
            if len(place) < 2:
                self._send_json(400, {"success": False, "error": "Please enter your place."})
                return
            if not re.match(r"^(19[5-9]\d|20[0-2]\d)(\s*[-–/]\s*(19[5-9]\d|20[0-2]\d|\d{2}))?$", batch_year):
                self._send_json(400, {"success": False, "error": "Please enter a valid 4-digit Batch Year."})
                return

            phone_res = normalize_indian_phone(whatsapp_number)
            if not phone_res["isValid"]:
                self._send_json(400, {"success": False, "error": phone_res["error"]})
                return

            if participation not in ("പങ്കെടുക്കും", "സാധിക്കില്ല"):
                self._send_json(400, {"success": False, "error": "Please select a valid participation option."})
                return

            records = load_db()

            # Guard against accidental immediate double-submissions (within 5 seconds)
            now_dt = datetime.now()
            norm_name = name.lower()
            norm_place = place.title()
            for existing in records[:5]:
                if (
                    str(existing.get("name", "")).strip().lower() == norm_name
                    and str(existing.get("place", "")).strip().title() == norm_place
                    and str(existing.get("batchYear", "")).strip() == batch_year
                    and str(existing.get("waNumber", "")).strip() == phone_res["waNumber"]
                    and str(existing.get("participation", "")).strip() == participation
                ):
                    try:
                        prev_dt = datetime.strptime(str(existing.get("timestamp", "")), "%Y-%m-%d %H:%M:%S")
                        if abs((now_dt - prev_dt).total_seconds()) <= 5:
                            self._send_json(
                                409,
                                {
                                    "success": False,
                                    "duplicate": True,
                                    "error": "Duplicate submission detected. Your registration was already saved a moment ago.",
                                },
                            )
                            return
                    except Exception:
                        pass

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
                    "place": place,
                    "batchYear": batch_year,
                    "whatsappNumber": whatsapp_number,
                    "participation": participation,
                }
            )
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
                    "storageMode": get_storage_mode(),
                    "registrationId": new_rec["registrationId"],
                    "confirmationMessage": EXACT_CONFIRMATION_MESSAGE,
                    "name": new_rec["name"],
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
