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

import hashlib
import hmac
import http.cookies
import json
import mimetypes
import os
import re
import secrets
import time
import urllib.parse
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

WORKSPACE_DIR = Path(__file__).resolve().parent
DB_FILE = WORKSPACE_DIR / "registrations_db.json"

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

# Active server-side sessions: token -> {"username": str, "expires_at": float}
ACTIVE_SESSIONS: dict[str, dict] = {}
SESSION_TTL_SECONDS = 8 * 3600  # 8 hours
SESSION_COOKIE_NAME = "aufbruch_admin_session"

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


def load_db() -> list[dict]:
    if not DB_FILE.exists():
        seeded = [enrich_registration(r) for r in DEFAULT_SEED_DATA]
        save_db(seeded)
        return seeded
    try:
        data = json.loads(DB_FILE.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return [enrich_registration(r) for r in data]
    except Exception:
        pass
    seeded = [enrich_registration(r) for r in DEFAULT_SEED_DATA]
    save_db(seeded)
    return seeded


def save_db(records: list[dict]) -> None:
    DB_FILE.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")


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
    token = secrets.token_urlsafe(32)
    ACTIVE_SESSIONS[token] = {
        "username": username,
        "expires_at": time.time() + SESSION_TTL_SECONDS,
    }
    return token


def get_valid_session(handler: BaseHTTPRequestHandler) -> dict | None:
    token = None

    # 1. Check Authorization Bearer header
    auth_header = handler.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:].strip()

    # 2. Check HttpOnly Cookie
    if not token:
        cookie_header = handler.headers.get("Cookie", "")
        if cookie_header:
            jar = http.cookies.SimpleCookie()
            try:
                jar.load(cookie_header)
                if SESSION_COOKIE_NAME in jar:
                    token = jar[SESSION_COOKIE_NAME].value
            except Exception:
                pass

    if not token or token not in ACTIVE_SESSIONS:
        return None

    sess = ACTIVE_SESSIONS[token]
    if time.time() > sess["expires_at"]:
        ACTIVE_SESSIONS.pop(token, None)
        return None

    return {"token": token, **sess}


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

    def send_error(self, code, message=None, explain=None):
        """Ensure /api/ routes never emit default HTML error pages."""
        path = urllib.parse.urlparse(getattr(self, "path", "") or "").path
        accept = (self.headers.get("Accept", "") if self.headers else "") or ""
        if path.startswith("/api/") or "application/json" in accept:
            self._send_json(code, {"success": False, "error": message or f"HTTP {code} error"})
            return
        super().send_error(code, message, explain)

    def _send_json(self, status_code: int, payload: dict, extra_headers: list[tuple[str, str]] | None = None):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
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
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
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
        route = parsed.path

        try:
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

            # 3. Static File Serving (restrict access to .py, .json db, Code.gs)
            if route in ("/", "/index.html", "/Index.html"):
                file_path = WORKSPACE_DIR / "Index.html"
            else:
                rel = route.lstrip("/")
                file_path = (WORKSPACE_DIR / rel).resolve()
                if not str(file_path).startswith(str(WORKSPACE_DIR)):
                    self.send_error(403, "Forbidden")
                    return
                if file_path.name in ("registrations_db.json", "server.py"):
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
            self.end_headers()
            self.wfile.write(data)
        except Exception as exc:
            if route.startswith("/api/"):
                self._send_json(500, {"success": False, "error": f"Internal server error: {exc}"})
            else:
                self.send_error(500, "Internal Server Error")

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        route = parsed.path
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
            cookie_val = (
                f"{SESSION_COOKIE_NAME}={token}; HttpOnly; Path=/; Max-Age={SESSION_TTL_SECONDS}; SameSite=Strict"
            )
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
                ACTIVE_SESSIONS.pop(sess["token"], None)
            clear_cookie = f"{SESSION_COOKIE_NAME}=; HttpOnly; Path=/; Max-Age=0; SameSite=Strict"
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
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "name": name,
                    "place": place,
                    "batchYear": batch_year,
                    "whatsappNumber": whatsapp_number,
                    "participation": participation,
                }
            )
            records.insert(0, new_rec)
            save_db(records)

            self._send_json(
                200,
                {
                    "success": True,
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


def run_server(port: int = 8765):
    load_db()
    server = ThreadingHTTPServer(("0.0.0.0", port), AufbruchRequestHandler)
    print(f"Aufbruch 2026 Secure Server listening on http://localhost:{port}")
    server.serve_forever()


if __name__ == "__main__":
    run_server(8765)
