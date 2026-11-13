"""
Automated verification test suite for the Aufbruch – Alumni Conclave 2026
Registration System:
- Indian Phone Validation & +91 Normalization
- Malayalam WhatsApp Message & Click-to-Chat URL Generation
- Strict Suppression for Non-Participating ("സാധിക്കില്ല")
- UI Structure Checks (Centered Form Only, No WhatsApp Preview Sidebar,
  No Event Details Page, No Administration & Sync Page, Sora Typography)
- Backend Admin Authentication, Route Protection & Session Management
"""

import json
import re
import unittest
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

WORKSPACE_DIR = Path(__file__).resolve().parent
BASE_URL = "http://localhost:8765"


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
            "error": "Invalid Indian mobile number.",
        }

    return {
        "isValid": True,
        "nationalNumber": national,
        "waNumber": "91" + national,
        "e164": "+91" + national,
        "display": f"+91 {national[:5]} {national[5:]}",
        "error": None,
    }


def build_whatsapp_message(name: str) -> str:
    clean_name = str(name or "Alumni Member").strip()
    return (
        "അസ്സലാമു അലൈകും\n\n"
        f"Hi... *{clean_name}*\n\n"
        "നിങ്ങൾ അൻവാർ അലുംനി കോൺക്ലൈവിൽ രജിസ്റ്റർ ചെയ്തതിന് നന്ദി...\n\n"
        "*ഡിസംബർ 10 വൈകിട്ട് 3:30 മുതൽ രാത്രി 9:30 വരെ* നടക്കുന്ന സംഗമത്തിൽ പങ്കാളിത്തം ഉറപ്പ് വരുത്തുക."
    )


def generate_whatsapp_confirmation_data(name: str, raw_phone: str, participation: str) -> dict:
    choice = str(participation or "").strip()
    if choice == "സാധിക്കില്ല" or choice != "പങ്കെടുക്കും":
        return {
            "shouldSend": False,
            "phoneData": normalize_indian_phone(raw_phone),
            "message": "",
            "clickToChatUrl": "",
        }

    phone_data = normalize_indian_phone(raw_phone)
    if not phone_data["isValid"]:
        return {
            "shouldSend": False,
            "phoneData": phone_data,
            "message": "",
            "clickToChatUrl": "",
        }

    msg = build_whatsapp_message(name)
    encoded = urllib.parse.quote(msg, safe="")
    return {
        "shouldSend": True,
        "phoneData": phone_data,
        "message": msg,
        "clickToChatUrl": f"https://wa.me/{phone_data['waNumber']}?text={encoded}",
    }


def http_json_request(path: str, method: str = "GET", payload: dict | None = None, headers: dict | None = None):
    req_headers = {"Content-Type": "application/json"}
    if headers:
        req_headers.update(headers)
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(f"{BASE_URL}{path}", data=data, headers=req_headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8")), dict(resp.headers)
    except urllib.error.HTTPError as err:
        body = err.read().decode("utf-8")
        return err.code, json.loads(body) if body else {}, dict(err.headers)


class TestAufbruchRegistrationSystem(unittest.TestCase):
    def test_indian_phone_formats_accepted(self):
        valid_inputs = [
            "9876543210",
            "+919876543210",
            "+91 9876543210",
            "+91 98765 43210",
            "+91-98765-43210",
            "919876543210",
            "09876543210",
            "8123456789",
            "7012345678",
            "6234567890",
        ]
        for raw in valid_inputs:
            res = normalize_indian_phone(raw)
            self.assertTrue(res["isValid"], f"Expected {raw} to be valid")
            self.assertTrue(res["waNumber"].startswith("91"))
            self.assertEqual(len(res["waNumber"]), 12)

    def test_invalid_phone_numbers_rejected(self):
        invalid_inputs = [
            "",
            "12345",
            "5876543210",  # Starts with 5 (not 6-9)
            "987654321",   # 9 digits
            "98765432100", # 11 digits not starting with 0
            "+1 9876543210",
            "abcdefghij",
        ]
        for raw in invalid_inputs:
            res = normalize_indian_phone(raw)
            self.assertFalse(res["isValid"], f"Expected {raw} to be invalid")

    def test_whatsapp_message_exact_malayalam_content(self):
        msg = build_whatsapp_message("Muhammed Anwar")
        expected = (
            "അസ്സലാമു അലൈകും\n\n"
            "Hi... *Muhammed Anwar*\n\n"
            "നിങ്ങൾ അൻവാർ അലുംനി കോൺക്ലൈവിൽ രജിസ്റ്റർ ചെയ്തതിന് നന്ദി...\n\n"
            "*ഡിസംബർ 10 വൈകിട്ട് 3:30 മുതൽ രാത്രി 9:30 വരെ* നടക്കുന്ന സംഗമത്തിൽ പങ്കാളിത്തം ഉറപ്പ് വരുത്തുക."
        )
        self.assertEqual(msg, expected)

    def test_participating_member_generates_click_to_chat_url(self):
        res = generate_whatsapp_confirmation_data(
            "Muhammed Anwar", "+91 98765 43210", "പങ്കെടുക്കും"
        )
        self.assertTrue(res["shouldSend"])
        self.assertTrue(
            res["clickToChatUrl"].startswith("https://wa.me/919876543210?text=")
        )
        decoded_text = urllib.parse.unquote(
            res["clickToChatUrl"].split("?text=", 1)[1]
        )
        self.assertIn("Hi... *Muhammed Anwar*", decoded_text)
        self.assertIn("അസ്സലാമു അലൈകും", decoded_text)

    def test_non_participating_member_strictly_suppressed(self):
        res = generate_whatsapp_confirmation_data(
            "Abdul Rasheed", "+91 98765 43210", "സാധിക്കില്ല"
        )
        self.assertFalse(res["shouldSend"])
        self.assertEqual(res["clickToChatUrl"], "")
        self.assertEqual(res["message"], "")

    def test_ui_sections_and_no_exposed_credentials(self):
        code_gs = (WORKSPACE_DIR / "Code.gs").read_text(encoding="utf-8")
        index_html = (WORKSPACE_DIR / "public" / "index.html").read_text(encoding="utf-8")

        # 1. Verify Registration Form is centered and WhatsApp Preview sidebar + box below it are removed
        self.assertIn("registration-centered-container", index_html)
        self.assertNotIn("Live WhatsApp Message Preview", index_html)
        self.assertNotIn("Automated Workflow Guarantees", index_html)
        self.assertNotIn("preview-sidebar", index_html)

        # 2. Verify Event Details page & nav item are completely removed
        self.assertNotIn("Event Details", index_html)
        self.assertNotIn('id="overview"', index_html)
        self.assertNotIn("Event Schedule & Highlights", index_html)

        # 3. Verify Administration & SYNC page & nav item are completely removed
        self.assertNotIn("Administration & Sync", index_html)
        self.assertNotIn("Google Sheets & Setup", index_html)
        self.assertNotIn('id="integration"', index_html)

        # 4. Verify Secure Admin Login UI & Logout button exist, and NO credentials/data are in Index.html
        self.assertIn('id="adminLoginSection"', index_html)
        self.assertIn('id="adminUsername"', index_html)
        self.assertIn('id="adminPassword"', index_html)
        self.assertIn('id="adminLoginBtn"', index_html)
        self.assertIn('id="adminLogoutBtn"', index_html)
        self.assertNotIn("Aufbruch@2026", index_html)
        self.assertNotIn("DEFAULT_SEED_DATA", index_html)

        # 5. Verify Sora font & existing features remain intact
        self.assertIn("Sora-Regular.ttf", index_html)
        self.assertIn("Sora-Light.ttf", index_html)
        self.assertIn("--font-primary: 'Sora'", index_html)
        self.assertIn("Designed by: Ajmal Kattichira", index_html)
        self.assertIn("authenticateAdminFromWebApp", code_gs)
        self.assertIn("logoutAdminFromWebApp", code_gs)

        # 6. Verify Admin Edit & Delete UI & Google Sheets Sync handlers exist
        self.assertIn("<th>Actions</th>", index_html)
        self.assertIn('id="editRegistrationModal"', index_html)
        self.assertIn('id="deleteConfirmModal"', index_html)
        self.assertIn("Are you sure you want to delete this registration?", index_html)
        self.assertIn("Save Changes", index_html)
        self.assertIn("Confirm Delete", index_html)
        self.assertIn("updateRegistrationFromAdmin", code_gs)
        self.assertIn("deleteRegistrationFromAdmin", code_gs)

        # 7. Verify Custom Submission Alert Modal & Footer Opacity (50%)
        self.assertIn('id="submissionAlertModal"', index_html)
        self.assertIn('id="submissionAlertBox"', index_html)
        self.assertIn('id="submissionAlertOkBtn"', index_html)
        self.assertIn("#171A22", index_html)
        self.assertIn("#FFC21A", index_html)
        self.assertIn("#FF9800", index_html)
        self.assertIn("isSubmitting", index_html)
        self.assertIn("apiFetchJson", index_html)
        self.assertIn("openSubmissionErrorModal", index_html)
        self.assertNotIn("alert(res.confirmationMessage", index_html)
        self.assertNotIn("window.alert(", index_html)
        self.assertIn("opacity: 0.5", index_html)

        # 8. Verify Updated Success Flow & Admin View / Individual Send Message Modals
        self.assertIn("Your registration has been submitted successfully. Thank you for registering.", index_html)
        self.assertIn("navigateToHomePageTop", index_html)
        self.assertIn('id="viewRegistrationModal"', index_html)
        self.assertIn('id="sendMessageModal"', index_html)
        self.assertIn('id="adminCustomMessageInput"', index_html)
        self.assertIn('id="confirmSendWaBtn"', index_html)
        self.assertIn("action-view-btn", index_html)
        self.assertIn("action-edit-btn", index_html)
        self.assertIn("action-delete-btn", index_html)
        self.assertIn("action-message-btn", index_html)

        # 9. Verify Object/JSON Display Guards, Session Endpoint Integration, Routing & Deployment Files
        self.assertIn("extractReadableMessage", index_html)
        self.assertIn("safeDisplayText", index_html)
        self.assertIn("syncRouteFromLocation", index_html)
        self.assertIn("/api/admin/session", index_html)
        self.assertIn("/fonts/Sora-Regular.ttf", index_html)
        self.assertNotIn("./fonts/Sora-", index_html)
        self.assertTrue((WORKSPACE_DIR / "public" / "index.html").exists())
        self.assertTrue((WORKSPACE_DIR / "public" / "fonts" / "Sora-Regular.ttf").exists())
        self.assertTrue((WORKSPACE_DIR / "vercel.json").exists())
        self.assertTrue((WORKSPACE_DIR / "api" / "index.py").exists())
        self.assertTrue((WORKSPACE_DIR / "Procfile").exists())

        vercel_cfg = json.loads((WORKSPACE_DIR / "vercel.json").read_text(encoding="utf-8"))
        self.assertIsNone(vercel_cfg.get("framework"))
        self.assertEqual(vercel_cfg.get("outputDirectory"), "public")
        inc = vercel_cfg.get("functions", {}).get("api/index.py", {}).get("includeFiles", "")
        self.assertIn("server.py", inc)
        self.assertIn("registrations_db.json", inc)
        dests = [r.get("destination", "") for r in vercel_cfg.get("rewrites", [])]
        self.assertIn("/index.html", dests)
        self.assertIn("/api/index.py?__route=$1", dests)
        self.assertNotIn("/Index.html", dests)

    def test_backend_admin_auth_and_protected_routes(self):
        # 1. Unauthenticated requests to dashboard, update, and delete must be rejected with 401
        status, body, _ = http_json_request("/api/admin/dashboard", "GET")
        self.assertEqual(status, 401)
        self.assertFalse(body.get("success", True))

        status_upd_unauth, _, _ = http_json_request(
            "/api/admin/update",
            "POST",
            {
                "registrationId": "001",
                "name": "Unauthorized Edit",
                "place": "Nilambur",
                "batchYear": "2018",
                "whatsappNumber": "9876543210",
                "participation": "പങ്കെടുക്കും",
            },
        )
        self.assertEqual(status_upd_unauth, 401)

        status_del_unauth, _, _ = http_json_request(
            "/api/admin/delete",
            "POST",
            {"registrationId": "001"},
        )
        self.assertEqual(status_del_unauth, 401)

        # 2. Invalid login attempt must be rejected with 401
        status, body, _ = http_json_request(
            "/api/admin/login",
            "POST",
            {"username": "admin", "password": "wrong_password"},
        )
        self.assertEqual(status, 401)
        self.assertFalse(body.get("authenticated", True))

        # 3. Valid login attempt must succeed with 200 and return sessionToken + HttpOnly cookie
        status, body, headers = http_json_request(
            "/api/admin/login",
            "POST",
            {"username": "admin", "password": "Aufbruch@2026"},
        )
        self.assertEqual(status, 200)
        self.assertTrue(body.get("authenticated"))
        token = body.get("sessionToken")
        self.assertTrue(token)
        cookie_hdr = headers.get("Set-Cookie", "")
        self.assertIn("HttpOnly", cookie_hdr)
        auth_headers = {"Authorization": f"Bearer {token}"}

        # 4. Authenticated request to /api/admin/dashboard must succeed with 200
        status, dash_body, _ = http_json_request(
            "/api/admin/dashboard",
            "GET",
            headers=auth_headers,
        )
        self.assertEqual(status, 200)
        self.assertTrue(dash_body.get("success"))
        self.assertIn("registrations", dash_body)
        self.assertIn("stats", dash_body)

        # 5. Create a temporary registration, verify strict JSON schema, then Edit & Delete it as Admin
        reg_status, reg_res, reg_headers = http_json_request(
            "/api/register",
            "POST",
            {
                "name": "Temp Alumni Test",
                "place": "Nilambur",
                "batchYear": "2019",
                "whatsappNumber": "9747380130",
                "participation": "പങ്കെടുക്കും",
            },
        )
        self.assertEqual(reg_status, 200)
        self.assertIn("application/json", reg_headers.get("Content-Type", ""))
        self.assertTrue(reg_res.get("success"))
        self.assertEqual(reg_res.get("message"), "Registration completed successfully")
        self.assertIsInstance(reg_res.get("data"), dict)
        created_id = reg_res["registrationId"]

        # Verify rapid duplicate submission returns HTTP 409 JSON without creating duplicate row
        dup_status, dup_res, dup_headers = http_json_request(
            "/api/register",
            "POST",
            {
                "name": "Temp Alumni Test",
                "place": "Nilambur",
                "batchYear": "2019",
                "whatsappNumber": "9747380130",
                "participation": "പങ്കെടുക്കും",
            },
        )
        self.assertEqual(dup_status, 409)
        self.assertIn("application/json", dup_headers.get("Content-Type", ""))
        self.assertFalse(dup_res.get("success", True))
        self.assertTrue(dup_res.get("duplicate"))

        # Verify invalid payload returns HTTP 400 with application/json and both message & error
        bad_status, bad_res, bad_headers = http_json_request(
            "/api/register",
            "POST",
            {"name": "A", "place": "Nilambur", "batchYear": "2019", "whatsappNumber": "123", "participation": "പങ്കെടുക്കും"},
        )
        self.assertEqual(bad_status, 400)
        self.assertIn("application/json", bad_headers.get("Content-Type", ""))
        self.assertFalse(bad_res.get("success", True))
        self.assertTrue(bad_res.get("message"))

        # Verify unknown /api/* route & unsupported method return JSON 404/405 (never HTML)
        notfound_status, notfound_res, notfound_headers = http_json_request("/api/nonexistent", "GET")
        self.assertEqual(notfound_status, 404)
        self.assertIn("application/json", notfound_headers.get("Content-Type", ""))
        self.assertFalse(notfound_res.get("success", True))

        method_status, method_res, method_headers = http_json_request("/api/register", "PUT", {})
        self.assertEqual(method_status, 405)
        self.assertIn("application/json", method_headers.get("Content-Type", ""))
        self.assertFalse(method_res.get("success", True))

        # 5A. Edit the registration via /api/admin/update
        upd_status, upd_body, _ = http_json_request(
            "/api/admin/update",
            "POST",
            {
                "registrationId": created_id,
                "name": "Temp Alumni Edited",
                "place": "Calicut",
                "batchYear": "2021",
                "whatsappNumber": "+91 8606140996",
                "participation": "സാധിക്കില്ല",
            },
            headers=auth_headers,
        )
        self.assertEqual(upd_status, 200)
        self.assertTrue(upd_body.get("success"))
        self.assertEqual(upd_body["updatedRecord"]["name"], "Temp Alumni Edited")
        self.assertEqual(upd_body["updatedRecord"]["place"], "Calicut")
        self.assertEqual(upd_body["updatedRecord"]["batchYear"], "2021")
        self.assertEqual(upd_body["updatedRecord"]["participation"], "സാധിക്കില്ല")
        self.assertFalse(upd_body["updatedRecord"]["shouldSendWhatsApp"])

        # 5B. Delete the registration via /api/admin/delete
        del_status, del_body, _ = http_json_request(
            "/api/admin/delete",
            "POST",
            {"registrationId": created_id},
            headers=auth_headers,
        )
        self.assertEqual(del_status, 200)
        self.assertTrue(del_body.get("success"))
        remaining_ids = [r["registrationId"] for r in del_body.get("registrations", [])]
        self.assertNotIn(created_id, remaining_ids)

        # 6. Logout must invalidate the session token immediately
        status, out_body, _ = http_json_request(
            "/api/admin/logout",
            "POST",
            headers=auth_headers,
        )
        self.assertEqual(status, 200)
        self.assertFalse(out_body.get("authenticated", True))

        # 7. Subsequent requests with logged-out token must return 401 Unauthorized
        status, _, _ = http_json_request(
            "/api/admin/dashboard",
            "GET",
            headers=auth_headers,
        )
        self.assertEqual(status, 401)

        sess_out_status, sess_out_body, _ = http_json_request(
            "/api/admin/session",
            "GET",
            headers=auth_headers,
        )
        self.assertEqual(sess_out_status, 401)
        self.assertFalse(sess_out_body.get("authenticated", True))

    def test_admin_session_and_spa_routes(self):
        # Unauthenticated session check must return 401 JSON
        status, sess_unauth, sess_hdrs = http_json_request("/api/admin/session", "GET")
        self.assertEqual(status, 401)
        self.assertIn("application/json", sess_hdrs.get("Content-Type", ""))
        self.assertFalse(sess_unauth.get("authenticated", True))

        # Login with cookie jar & verify session + dashboard persistence
        import http.cookiejar
        cj = http.cookiejar.CookieJar()
        opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
        login_req = urllib.request.Request(
            f"{BASE_URL}/api/admin/login",
            data=json.dumps({"username": "admin", "password": "Aufbruch@2026"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with opener.open(login_req, timeout=5) as resp:
            self.assertEqual(resp.status, 200)
            login_json = json.loads(resp.read().decode("utf-8"))
            self.assertTrue(login_json.get("authenticated"))

        with opener.open(f"{BASE_URL}/api/admin/session", timeout=5) as resp:
            self.assertEqual(resp.status, 200)
            sess_json = json.loads(resp.read().decode("utf-8"))
            self.assertTrue(sess_json.get("authenticated"))
            self.assertEqual(sess_json.get("username"), "admin")

        # Logout via cookie jar
        logout_req = urllib.request.Request(
            f"{BASE_URL}/api/admin/logout",
            data=b"{}",
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with opener.open(logout_req, timeout=5) as resp:
            self.assertEqual(resp.status, 200)

        # SPA HTML routes must serve UI HTML (not 404 or raw JSON)
        for route in ["/", "/index.html", "/register", "/register/", "/dashboard", "/dashboard/", "/admin", "/admin/", "/admin/login", "/admin/login/"]:
            with urllib.request.urlopen(f"{BASE_URL}{route}", timeout=5) as resp:
                self.assertEqual(resp.status, 200)
                self.assertIn("text/html", resp.headers.get("Content-Type", ""))
                body_preview = resp.read(256).decode("utf-8", errors="ignore")
                self.assertIn("<!DOCTYPE html>", body_preview)

        # Static fonts must load with HTTP 200 and sensitive files must NOT be publicly served
        with urllib.request.urlopen(f"{BASE_URL}/fonts/Sora-Regular.ttf", timeout=5) as resp:
            self.assertEqual(resp.status, 200)
            self.assertGreater(len(resp.read()), 10000)

        for secret_path in ["/registrations_db.json", "/server.py", "/Code.gs", "/vercel.json"]:
            with self.assertRaises(urllib.error.HTTPError) as ctx:
                urllib.request.urlopen(f"{BASE_URL}{secret_path}", timeout=5)
            self.assertIn(ctx.exception.code, (403, 404))

        # Health endpoint and Vercel-rewritten ?__route= dispatch must return valid JSON
        h_status, h_body, h_hdrs = http_json_request("/api/health", "GET")
        self.assertEqual(h_status, 200)
        self.assertIn("application/json", h_hdrs.get("Content-Type", ""))
        self.assertTrue(h_body.get("success"))
        self.assertEqual(h_body.get("status"), "ok")
        self.assertNotIn("registrations", h_body)

        rw_status, rw_body, rw_hdrs = http_json_request("/api/index.py?__route=admin/session", "GET")
        self.assertEqual(rw_status, 401)
        self.assertIn("application/json", rw_hdrs.get("Content-Type", ""))
        self.assertFalse(rw_body.get("authenticated", True))

        # Verify Vercel serverless handler import and subclass inheritance
        from http.server import BaseHTTPRequestHandler
        import api.index as vercel_api
        self.assertTrue(issubclass(vercel_api.handler, BaseHTTPRequestHandler))


if __name__ == "__main__":
    unittest.main(verbosity=2)
