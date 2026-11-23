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
import os
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
        self.assertIn("© 2026 Ajmal Kattichira. All Rights Reserved.", index_html)
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
        self.assertIn('id="waDeliveryConfirmBox"', index_html)
        self.assertIn('id="confirmWaDeliveredBtn"', index_html)
        self.assertIn('id="cancelWaDeliveredBtn"', index_html)
        self.assertIn("action-view-btn", index_html)
        self.assertIn("action-edit-btn", index_html)
        self.assertIn("action-delete-btn", index_html)
        self.assertIn("action-message-btn", index_html)
        self.assertIn(".action-message-btn.wa-sent", index_html)
        self.assertIn("opacity: 0.45", index_html)
        self.assertIn("/api/admin/whatsapp-status", index_html)
        self.assertNotIn("Send WhatsApp to ", index_html)
        self.assertNotIn("<th>WhatsApp Confirmation Action</th>", index_html)

        # 8B. Verify New Field Order (1. Batch Year first, 2. Name second), Edit Name, Batch Report & QR Scanner UI
        batch_label_pos = index_html.find("1. Batch Year")
        name_label_pos = index_html.find("2. Name")
        place_label_pos = index_html.find("3. Place")
        self.assertGreater(batch_label_pos, 0)
        self.assertGreater(name_label_pos, batch_label_pos)
        self.assertGreater(place_label_pos, name_label_pos)
        for yr in range(2001, 2027):
            self.assertIn(f'<option value="{yr}">{yr}</option>', index_html)
        self.assertIn("Name not correct? Edit Name", index_html)
        self.assertIn('id="studentSelect"', index_html)
        self.assertIn('id="shareBatchReportWaBtn"', index_html)
        self.assertIn("SHARE BATCH REPORT ON WHATSAPP", index_html)
        self.assertIn("EVENT CHECK-IN / QR SCANNER", index_html)
        self.assertIn("CONFIRM TICKET", index_html)
        self.assertIn("TICKET CONFIRMED SUCCESSFULLY", index_html)
        self.assertIn("ANWAR ALUMNI SEAT CONFIRMED!", index_html)
        self.assertIn("ALREADY CONFIRMED – ENTRY COMPLETED", index_html)
        self.assertIn("INVALID TICKET – ACCESS DENIED", index_html)
        self.assertIn("Are you sure you want to confirm this ticket?", index_html)
        self.assertNotIn("Step 1 of 2 •", index_html)
        self.assertNotIn("ticketPassStatus", index_html)
        self.assertNotIn("ticketPassStubId", index_html)
        self.assertNotIn("Present this QR Code at the registration desk for one-time check-in", index_html)
        self.assertIn("Download Ticket", index_html)
        self.assertIn("View Ticket", index_html)
        self.assertIn("Print Ticket", index_html)
        self.assertIn("/vendor/jsQR.js", index_html)
        self.assertIn("jsQR", index_html)
        self.assertIn('id="qrCameraSelect"', index_html)
        self.assertIn('id="checkinKpiWaSent"', index_html)
        self.assertIn('id="checkinKpiWaFailed"', index_html)
        self.assertIn('id="filterCheckinWaStatusSelect"', index_html)

        # 9. Verify Object/JSON Display Guards, Session Endpoint Integration, Routing & Deployment Files
        self.assertIn("extractReadableMessage", index_html)
        self.assertIn("safeDisplayText", index_html)
        self.assertIn("syncRouteFromLocation", index_html)
        self.assertIn("/api/admin/session", index_html)
        self.assertIn("/fonts/Sora-Regular.ttf", index_html)
        self.assertNotIn("./fonts/Sora-", index_html)
        self.assertIn('id="step1BatchSection"', index_html)
        self.assertIn('id="step2NameSection"', index_html)
        self.assertIn('id="step2RemainingSection"', index_html)
        self.assertIn('id="studentComboboxContainer"', index_html)
        self.assertNotIn("Type to search your name in the selected batch", index_html)
        self.assertIn('id="ticketPassHeaderId"', index_html)
        # 12. Verify Open Graph (WhatsApp/Facebook/Telegram) & Twitter Card metadata + public 1200x630 preview image
        self.assertIn('<meta property="og:title" content="AUFBRUCH ALUMNI CONCLAVE 2026" />', index_html)
        self.assertIn('<meta property="og:description" content="Majmau Ssaqafathil Islamiyya, Nilambur" />', index_html)
        self.assertIn('<meta property="og:image" content="https://anwar-alumni-conclave.vercel.app/aufbruch-og-preview.jpg" />', index_html)
        self.assertIn('<meta property="og:image:width" content="1200" />', index_html)
        self.assertIn('<meta property="og:image:height" content="630" />', index_html)
        self.assertIn('<meta property="og:url" content="https://anwar-alumni-conclave.vercel.app/" />', index_html)
        self.assertIn('<meta property="og:type" content="website" />', index_html)
        self.assertIn('property="og:site_name"', index_html)
        self.assertIn('<meta name="twitter:card" content="summary_large_image" />', index_html)
        self.assertIn('<meta name="twitter:title" content="AUFBRUCH ALUMNI CONCLAVE 2026" />', index_html)
        self.assertIn('<meta name="twitter:description" content="Majmau Ssaqafathil Islamiyya, Nilambur" />', index_html)
        self.assertIn('<meta name="twitter:image" content="https://anwar-alumni-conclave.vercel.app/aufbruch-og-preview.jpg" />', index_html)
        self.assertTrue((WORKSPACE_DIR / "public" / "aufbruch-og-preview.jpg").exists())
        # 13. Verify Unified CHECKED IN STUDENTS portal, S.No., Checked Status badges & Place-wise Chart removal
        self.assertIn('id="checkedInStudentsSection"', index_html)
        self.assertNotIn('id="notCheckedInStudentsSection"', index_html)
        self.assertIn('id="checkedInStudentsTableBody"', index_html)
        self.assertNotIn('id="notCheckedInStudentsTableBody"', index_html)
        self.assertIn('id="searchCheckinTicketInput"', index_html)
        self.assertIn("CHECKED IN STUDENTS", index_html)
        self.assertIn("S.No.", index_html)
        self.assertIn("Checked Status", index_html)
        self.assertIn("status-badge-checked-in", index_html)
        self.assertIn("status-badge-not-checked-in", index_html)
        self.assertIn("🟢 CHECKED-IN", index_html)
        self.assertIn("🔴 NOT CHECKED IN", index_html)
        self.assertIn('id="successModalCheckedStatus"', index_html)
        self.assertNotIn("Place-wise Registration Count", index_html)
        self.assertNotIn('id="placeChartContainer"', index_html)
        # 10. Verify Sticky Navbar exclusivity (no top Register button), Red Hero Register Now CTA, Celebration & Conditional Screen
        self.assertNotIn('id="heroDashboardBtn"', index_html)
        self.assertNotIn('id="navRegisterBtn"', index_html)
        self.assertNotIn("Complete Registration", index_html)
        body_part = index_html.split("<body", 1)[1].split("<script", 1)[0]
        self.assertEqual(body_part.count("Admin Dashboard"), 1)
        self.assertIn('id="heroRegisterBtn"', index_html)
        self.assertIn("btn-hero-register-red", index_html)
        self.assertIn("<span>Register Now</span>", index_html)
        self.assertIn('id="registrationWishesBanner"', index_html)
        self.assertIn("Welcome to ANWAR ALUMNI CONCLAVE!", index_html)
        self.assertIn('id="ticketCelebrationStage"', index_html)
        self.assertIn('id="celebrationRibbonBanner"', index_html)
        self.assertIn("triggerTicketCelebration", index_html)
        self.assertIn("#DC2626", index_html)
        self.assertNotIn("event-pass-artwork-frame", index_html)
        self.assertIn("isTicketEligibleRecord", index_html)
        self.assertIn("REGISTRATION SUCCESSFUL!", index_html)
        self.assertIn("Thank you for registering with Aufbruch Alumni Conclave 2026.", index_html)
        self.assertIn("We appreciate your response. We hope to meet you at another event!", index_html)
        # 11. Verify Master Student Database renders NO students when set to None and reference ticket styling
        self.assertIn("Select a Batch Year above to display student records.", index_html)
        self.assertNotIn("? allMasterStudents.slice()", index_html)
        self.assertIn("OFFICIAL EVENT ENTRY TICKET", index_html)
        self.assertIn("Participant Name:", index_html)
        self.assertIn("ID Number:", index_html)
        self.assertIn("Batch Year:", index_html)
        self.assertIn('id="scannerTopNotificationBanner"', index_html)
        self.assertIn('<option value="NONE" selected>None</option>', index_html)
        self.assertIn('id="deleteStudentConfirmModal"', index_html)
        self.assertIn("Are you sure you want to remove this student?", index_html)
        self.assertNotIn('id="alumniUpdateReportSection"', index_html)
        self.assertNotIn("ALUMNI LIST UPDATE REPORT", index_html)
        self.assertIn('id="officialStudentTotalValue"', index_html)
        self.assertIn('id="downloadBatchReportBtn"', index_html)
        self.assertIn('id="nonRegisteredSharePanel"', index_html)
        self.assertIn('id="nonRegisteredBatchSelect"', index_html)
        self.assertIn('id="copyNonRegisteredBtn"', index_html)
        self.assertIn('id="shareNonRegisteredWaBtn"', index_html)
        self.assertIn('id="nonRegisteredListContainer"', index_html)
        self.assertIn("All members have completed registration. No pending members.", index_html)
        self.assertIn("> Alumni Conclave 2026", index_html)
        self.assertTrue((WORKSPACE_DIR / "alumni_list_corrected.xlsx").exists())
        self.assertFalse((WORKSPACE_DIR / "alumni list.xlsx").exists())
        self.assertTrue((WORKSPACE_DIR / "public" / "index.html").exists())
        self.assertTrue((WORKSPACE_DIR / "public" / "aufbruch_poster.png").exists())
        self.assertTrue((WORKSPACE_DIR / "public" / "vendor" / "jsQR.js").exists())
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
        self.assertIn("alumni_list_corrected.xlsx", inc)
        self.assertNotIn("alumni list.xlsx", inc)
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

        status_wa_unauth, _, _ = http_json_request(
            "/api/admin/whatsapp-status",
            "POST",
            {"registrationId": "001", "whatsappSent": True},
        )
        self.assertEqual(status_wa_unauth, 401)

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
        self.assertIn("batchReport", dash_body)
        self.assertIn("whatsappReportText", dash_body)
        self.assertEqual(dash_body.get("officialOverallTotal"), 302)
        self.assertEqual(dash_body["batchReport"].get("officialOverallTotal"), 302)
        self.assertEqual(len(dash_body["batchReport"]["batches"]), 26)
        self.assertIn("*Aufbruch*\n*Alumni Conclave 2026*", dash_body["whatsappReportText"])
        self.assertIn("/302 (", dash_body["whatsappReportText"])
        self.assertNotIn("/330 (", dash_body["whatsappReportText"])

        # 4B. Verify /api/students returns batch-filtered Excel names and dynamic batch totals from Students List
        st_status, st_2001, _ = http_json_request("/api/students?batchYear=2001", "GET")
        self.assertEqual(st_status, 200)
        self.assertEqual(len(st_2001.get("students", [])), 4)
        self.assertEqual(st_2001["officialBatchTotals"]["2001"], 4)
        self.assertEqual(st_2001["officialBatchTotals"]["2007"], 5)
        self.assertEqual(st_2001["officialBatchTotals"]["2026"], 12)
        self.assertEqual(st_2001["officialOverallTotal"], 302)
        self.assertEqual(sum(st_2001["officialBatchTotals"].values()), 302)

        _, st_2007, _ = http_json_request("/api/students?batchYear=2007", "GET")
        self.assertEqual(len(st_2007.get("students", [])), 5)

        _, st_2026, _ = http_json_request("/api/students?batchYear=2026", "GET")
        self.assertEqual(len(st_2026.get("students", [])), 12)
        self.assertIn("ANSHID MT", [s.get("name") for s in st_2026.get("students", [])])

        _, st_all, _ = http_json_request("/api/students", "GET")
        self.assertEqual(len(st_all.get("students", [])), 302)

        # 4C. Verify Automatic Batch Wise Registration Sync on Student Add & Delete (302 -> 303 -> 302)
        add_st_status, add_st_body, _ = http_json_request(
            "/api/admin/students/add",
            "POST",
            {"batchYear": "2001", "name": "TEMP BATCH SYNC TEST STUDENT"},
            headers=auth_headers,
        )
        self.assertEqual(add_st_status, 200)
        self.assertTrue(add_st_body.get("success"))
        added_stu_id = add_st_body["addedStudent"]["studentId"]
        self.assertEqual(len(add_st_body.get("students", [])), 303)
        self.assertEqual(add_st_body.get("officialOverallTotal"), 303)
        self.assertEqual(add_st_body["officialBatchTotals"]["2001"], 5)
        self.assertEqual(add_st_body["batchReport"]["officialOverallTotal"], 303)
        self.assertEqual(add_st_body["batchReport"]["batches"][0]["officialTotal"], 5)
        self.assertIn("/05 (", add_st_body["batchReport"]["batches"][0]["reportLine"])
        self.assertIn("/303 (", add_st_body["whatsappReportText"])
        self.assertIn("TEMP BATCH SYNC TEST STUDENT", add_st_body["batchReport"]["batches"][0]["nonRegisteredNames"])
        self.assertIn(
            "*Aufbruch*\n> Alumni Conclave 2026\n\n*Batch 2001*\nNon-Registered Members\n*Total Pending:",
            add_st_body["batchReport"]["batches"][0]["nonRegisteredWhatsappText"],
        )
        self.assertIn("\n\n________\n\n1. ", add_st_body["batchReport"]["batches"][0]["nonRegisteredWhatsappText"])

        del_st_status, del_st_body, _ = http_json_request(
            "/api/admin/students/delete",
            "POST",
            {"studentId": added_stu_id},
            headers=auth_headers,
        )
        self.assertEqual(del_st_status, 200)
        self.assertTrue(del_st_body.get("success"))
        self.assertEqual(len(del_st_body.get("students", [])), 302)
        self.assertEqual(del_st_body.get("officialOverallTotal"), 302)
        self.assertEqual(del_st_body["officialBatchTotals"]["2001"], 4)
        self.assertEqual(del_st_body["batchReport"]["officialOverallTotal"], 302)
        self.assertEqual(del_st_body["batchReport"]["batches"][0]["officialTotal"], 4)
        self.assertIn("/04 (", del_st_body["batchReport"]["batches"][0]["reportLine"])
        self.assertIn("/302 (", del_st_body["whatsappReportText"])
        self.assertNotIn("TEMP BATCH SYNC TEST STUDENT", del_st_body["batchReport"]["batches"][0]["nonRegisteredNames"])

        # Test Excel import with mode=replace verifies complete replacement
        import base64
        b64_excel = base64.b64encode((WORKSPACE_DIR / "alumni_list_corrected.xlsx").read_bytes()).decode("ascii")
        imp_status, imp_body, _ = http_json_request(
            "/api/admin/students/import",
            "POST",
            {"fileBase64": b64_excel, "fileName": "alumni_list_corrected.xlsx", "mode": "replace"},
            headers=auth_headers,
        )
        self.assertEqual(imp_status, 200)
        self.assertEqual(imp_body.get("importedCount"), 302)
        self.assertEqual(imp_body.get("officialOverallTotal"), 302)

        # Clean up any leftover temporary test records from an interrupted run
        for existing_r in dash_body.get("registrations", []):
            if "Temp Alumni" in str(existing_r.get("name", "")) or "Second Alumni" in str(existing_r.get("name", "")):
                http_json_request(
                    "/api/admin/delete",
                    "POST",
                    {"registrationId": existing_r["registrationId"]},
                    headers=auth_headers,
                )

        # 5. Create a temporary registration (with edited name), verify QR ticket & strict JSON schema
        reg_status, reg_res, reg_headers = http_json_request(
            "/api/register",
            "POST",
            {
                "name": "Temp Alumni Corrected",
                "originalExcelName": "Temp Alumni Original",
                "nameEdited": True,
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
        created_ticket_id = reg_res["ticketId"]
        created_token = reg_res["ticketToken"]
        self.assertTrue(created_ticket_id.startswith("ANWAR "))
        self.assertTrue(created_token.startswith("AUF26-ANWAR"))
        self.assertTrue(isinstance(reg_res.get("qrMatrix"), list) and len(reg_res["qrMatrix"]) >= 21)
        self.assertEqual(reg_res["data"]["originalExcelName"], "Temp Alumni Original")
        self.assertTrue(reg_res["data"]["nameEdited"])

        # Verify edited & resubmitted registration for the same student updates existing record in place and keeps status REGISTERED
        dup_status, dup_res, dup_headers = http_json_request(
            "/api/register",
            "POST",
            {
                "name": "Temp Alumni Corrected",
                "originalExcelName": "Temp Alumni Original",
                "place": "Nilambur",
                "batchYear": "2019",
                "whatsappNumber": "9747380130",
                "participation": "പങ്കെടുക്കും",
            },
        )
        self.assertEqual(dup_status, 200)
        self.assertIn("application/json", dup_headers.get("Content-Type", ""))
        self.assertTrue(dup_res.get("success"))
        self.assertTrue(dup_res.get("updatedExisting"))
        self.assertEqual(dup_res.get("registrationId"), created_id)
        self.assertEqual(dup_res.get("ticketId"), created_ticket_id)
        self.assertEqual(dup_res.get("registrationStatus"), "REGISTERED")

        # Verify edited-name reconciliation matches all edited student names to their official Master Student records
        import server as srv_mod
        master_students = srv_mod.load_students_db()
        edited_probe_records = [
            {"registrationId": "901", "batchYear": "2011", "name": "Muhammed Basheersaqafi", "originalExcelName": "Muhammed Basheersaqafi"},
            {"registrationId": "902", "batchYear": "2017", "name": "MUHAMMED SAFVAN SAQUAFI", "originalExcelName": "MUHAMMED SAFVAN SAQUAFI"},
            {"registrationId": "903", "batchYear": "2017", "name": "NAMEER SAQUAFI", "originalExcelName": "NAMEER SAQUAFI"},
            {"registrationId": "904", "batchYear": "2018", "name": "HIDAYATHULLA", "originalExcelName": "HIDAYATHULLA"},
            {"registrationId": "905", "batchYear": "2021", "name": "MUHAMMED ABOOBACKER SURAIJI", "originalExcelName": "MUHAMMED ABOOBACKER SURAIJI"},
            {"registrationId": "906", "batchYear": "2022", "name": "MUHAMMED ABU THWAHIR.M", "originalExcelName": "MUHAMMED ABU THWAHIR.M"},
            {"registrationId": "907", "batchYear": "2022", "name": "MUHAMMED SALIM KC", "originalExcelName": "MUHAMMED SALIM KC"},
            {"registrationId": "908", "batchYear": "2022", "name": "MOHAMMED SOLIH HADI", "originalExcelName": "MOHAMMED SOLIH HADI"},
            {"registrationId": "909", "batchYear": "2023", "name": "ABDUL RAHOOF NIZAMI", "originalExcelName": "ABDUL RAHOOF NIZAMI"},
            {"registrationId": "910", "batchYear": "2023", "name": "Muhammed hashir", "originalExcelName": "Muhammed hashir"},
            {"registrationId": "911", "batchYear": "2023", "name": "ABDUL BASITH ADANY", "originalExcelName": "ABDUL BASITH ADANY"},
            {"registrationId": "912", "batchYear": "2023", "name": "Muhammed Shafeeq K", "originalExcelName": "Muhammed Shafeeq K"},
            {"registrationId": "913", "batchYear": "2023", "name": "MUHAMMED SHEHEER SA'ADI", "originalExcelName": "MUHAMMED SHEHEER SA'ADI"},
            {"registrationId": "914", "batchYear": "2023", "name": "ABOOTHAHIR MUEENI KP", "originalExcelName": "ABOOTHAHIR MUEENI KP"},
            {"registrationId": "915", "batchYear": "2024", "name": "MUHAMMED SHAFI HADI", "originalExcelName": "MUHAMMED SHAFI HADI"},
            {"registrationId": "916", "batchYear": "2024", "name": "BISHR HADI", "originalExcelName": "BISHR HADI"},
            {"registrationId": "917", "batchYear": "2026", "name": "MUHAMMAD SABIQ K", "originalExcelName": "MUHAMMAD SABIQ K"},
        ]
        healed_probes, was_healed = srv_mod.reconcile_registrations_with_students(edited_probe_records, master_students)
        self.assertTrue(was_healed)
        for hp in healed_probes:
            self.assertTrue(hp.get("studentId"), f"Expected studentId to be resolved for {hp.get('name')}")
            self.assertEqual(hp.get("registrationStatus"), "REGISTERED")
        non_reg_map, _, _, _ = srv_mod.compute_batch_non_registered_map(healed_probes, master_students)
        self.assertNotIn("BASHEER SAQUAFI", [s["name"] for s in non_reg_map["2011"]])
        self.assertNotIn("NAMER SAQUAFI", [s["name"] for s in non_reg_map["2017"]])
        self.assertNotIn("HIDAYATHULLA SAQUAFI", [s["name"] for s in non_reg_map["2018"]])
        self.assertNotIn("ABUTHWAHIR SA'ADI", [s["name"] for s in non_reg_map["2022"]])
        self.assertNotIn("SALIM MUEENI", [s["name"] for s in non_reg_map["2022"]])
        self.assertNotIn("SWALIH HADI VETTIKKATTIRI", [s["name"] for s in non_reg_map["2022"]])
        self.assertNotIn("ABDUL RAHOOF HADI", [s["name"] for s in non_reg_map["2023"]])
        self.assertNotIn("HASHIR MUEENI", [s["name"] for s in non_reg_map["2023"]])
        self.assertNotIn("ABDUL BASITH HADI", [s["name"] for s in non_reg_map["2023"]])
        self.assertNotIn("SHAFEEQ ADANY", [s["name"] for s in non_reg_map["2023"]])
        self.assertNotIn("SHAHEER SA'ADI", [s["name"] for s in non_reg_map["2023"]])
        self.assertNotIn("ABU THWAHIR MUEENI", [s["name"] for s in non_reg_map["2023"]])
        self.assertNotIn("SHAFI HADI", [s["name"] for s in non_reg_map["2024"]])
        self.assertNotIn("MUHAMMED SABIQUE KA", [s["name"] for s in non_reg_map["2026"]])

        # 5-QR. Verify QR Scanner verification, Public Ticket Privacy & One-Time Check-in Confirmation
        # (a0) Public /api/ticket?token=... must NOT expose private phone numbers or WhatsApp links
        pub_t_status, pub_t_body, _ = http_json_request(f"/api/ticket?token={created_token}", "GET")
        self.assertEqual(pub_t_status, 200)
        self.assertTrue(pub_t_body.get("success"))
        pub_ticket = pub_t_body.get("ticket", {})
        self.assertEqual(pub_ticket.get("ticketId"), created_ticket_id)
        self.assertNotIn("whatsappNumber", pub_ticket)
        self.assertNotIn("formattedPhone", pub_ticket)
        self.assertNotIn("waNumber", pub_ticket)
        self.assertNotIn("whatsAppClickToChatUrl", pub_ticket)

        # (a) Invalid QR code must return INVALID TICKET – ACCESS DENIED
        inv_status, inv_body, _ = http_json_request(
            "/api/admin/checkin/verify",
            "POST",
            {"qrData": "FAKE-INVALID-QR-TOKEN-999"},
            headers=auth_headers,
        )
        self.assertEqual(inv_status, 200)
        self.assertFalse(inv_body.get("valid", True))
        self.assertEqual(inv_body.get("status"), "INVALID")
        self.assertEqual(inv_body.get("headline"), "INVALID TICKET – ACCESS DENIED")
        self.assertEqual(inv_body.get("toastHeadline"), "INVALID TICKET – ACCESS DENIED")

        # (b) Valid unconfirmed QR code must return VALID_PENDING & < TICKET CONFIRMED > + QR SCANNED SUCCESSFULLY
        ver_status, ver_body, _ = http_json_request(
            "/api/admin/checkin/verify",
            "POST",
            {"qrData": created_token},
            headers=auth_headers,
        )
        self.assertEqual(ver_status, 200)
        self.assertTrue(ver_body.get("valid"))
        self.assertFalse(ver_body.get("alreadyCheckedIn", True))
        self.assertEqual(ver_body.get("status"), "VALID_PENDING")
        self.assertEqual(ver_body.get("headline"), "< TICKET CONFIRMED >")
        self.assertEqual(ver_body.get("toastHeadline"), "QR SCANNED SUCCESSFULLY")
        self.assertEqual(ver_body["participant"]["ticketId"], created_ticket_id)
        self.assertTrue(ver_body["participant"].get("formattedPhone"))

        # Before check-in, CONFIRMED WhatsApp message must NOT be generated or allowed,
        # and marking regular whatsapp-status sent must NOT mark checkedIn=True
        self.assertEqual(ver_body["participant"].get("checkinWhatsappMessage"), "")
        self.assertEqual(ver_body["participant"].get("checkinWhatsappClickToChatUrl"), "")
        wa_only_status, wa_only_body, _ = http_json_request(
            "/api/admin/whatsapp-status",
            "POST",
            {"registrationId": created_id, "whatsappSent": True},
            headers=auth_headers,
        )
        self.assertEqual(wa_only_status, 200)
        self.assertFalse(wa_only_body["updatedRecord"]["checkedIn"])
        self.assertEqual(wa_only_body["updatedRecord"]["checkInStatus"], "NOT CHECKED IN")
        # Reset temporary regular whatsappSent state so downstream reminder count assertions start from 0
        http_json_request(
            "/api/admin/whatsapp-status",
            "POST",
            {"registrationId": created_id, "whatsappSent": False},
            headers=auth_headers,
        )
        pre_wa_status, _, _ = http_json_request(
            "/api/admin/checkin/whatsapp-manual",
            "POST",
            {"registrationId": created_id},
            headers=auth_headers,
        )
        self.assertEqual(pre_wa_status, 400)

        # (c) First check-in confirmation must succeed with 200, TICKET CONFIRMED SUCCESSFULLY & accurate WhatsApp status
        conf1_status, conf1_body, _ = http_json_request(
            "/api/admin/checkin/confirm",
            "POST",
            {"ticketToken": created_token},
            headers=auth_headers,
        )
        self.assertEqual(conf1_status, 200)
        self.assertTrue(conf1_body.get("success"))
        self.assertEqual(conf1_body.get("status"), "CONFIRMED_NOW")
        self.assertEqual(conf1_body.get("headline"), "TICKET CONFIRMED SUCCESSFULLY")
        self.assertEqual(conf1_body.get("subHeadline"), "ANWAR ALUMNI SEAT CONFIRMED!")
        self.assertTrue(conf1_body["participant"]["checkedIn"])
        self.assertEqual(conf1_body["participant"]["checkInStatus"], "CHECKED IN")
        first_checkin_ts = conf1_body.get("checkInTimestamp")
        self.assertTrue(first_checkin_ts)

        wa_info = conf1_body.get("checkinWhatsapp", {})
        self.assertIn("🛎️ *TICKET CONFIRMED...!*", wa_info.get("messageText", ""))
        self.assertIn("Assalamu Alaikum,\n*Temp Alumni Corrected*", wa_info.get("messageText", ""))
        self.assertIn("Your Entry for *AUFBRUCH ALUMNI CONCLAVE 2026* has been Successfully Confirmed. 🤝", wa_info.get("messageText", ""))
        self.assertIn("*Ticket Details:*", wa_info.get("messageText", ""))
        self.assertIn("- Status: CONFIRMED ✅", wa_info.get("messageText", ""))
        self.assertIn("*Majmau Ssaqafathil Islamiyya*\nDa'wa College Alumni", wa_info.get("messageText", ""))
        # Without Cloud API env vars configured, sent MUST be False and status MUST NOT falsely claim SENT
        if not wa_info.get("configured"):
            self.assertFalse(wa_info.get("sent", True))
            self.assertEqual(wa_info.get("status"), "NOT_CONFIGURED")
            self.assertTrue(wa_info.get("manualFallbackUrl", "").startswith("https://wa.me/91"))
            # First manual WhatsApp share succeeds; duplicate share on same check-in is blocked with 409
            m_wa1_status, m_wa1_body, _ = http_json_request(
                "/api/admin/checkin/whatsapp-manual",
                "POST",
                {"registrationId": created_id},
                headers=auth_headers,
            )
            self.assertEqual(m_wa1_status, 200)
            self.assertEqual(m_wa1_body["updatedRecord"]["checkinWhatsappStatus"], "MANUAL_FALLBACK")
            m_wa2_status, m_wa2_body, _ = http_json_request(
                "/api/admin/checkin/whatsapp-manual",
                "POST",
                {"registrationId": created_id},
                headers=auth_headers,
            )
            self.assertEqual(m_wa2_status, 409)
            self.assertTrue(m_wa2_body.get("alreadyNotified"))
            self.assertTrue(wa_info.get("manualFallbackUrl", "").startswith("https://wa.me/91"))

        # (d) Second check-in confirmation on the same ticket must be permanently blocked (HTTP 409)
        conf2_status, conf2_body, _ = http_json_request(
            "/api/admin/checkin/confirm",
            "POST",
            {"ticketToken": created_token},
            headers=auth_headers,
        )
        self.assertEqual(conf2_status, 409)
        self.assertFalse(conf2_body.get("success", True))
        self.assertTrue(conf2_body.get("alreadyCheckedIn"))
        self.assertEqual(conf2_body.get("status"), "ALREADY_CONFIRMED")
        self.assertEqual(conf2_body.get("headline"), "ALREADY CONFIRMED – ENTRY COMPLETED")
        self.assertEqual(conf2_body.get("checkInTimestamp"), first_checkin_ts)

        # (e) Re-scanning the already-confirmed QR code must return ALREADY CONFIRMED – ENTRY COMPLETED
        ver2_status, ver2_body, _ = http_json_request(
            "/api/admin/checkin/verify",
            "POST",
            {"qrData": created_token},
            headers=auth_headers,
        )
        self.assertEqual(ver2_status, 200)
        self.assertTrue(ver2_body.get("alreadyCheckedIn"))
        self.assertEqual(ver2_body.get("status"), "ALREADY_CONFIRMED")
        self.assertEqual(ver2_body.get("headline"), "ALREADY CONFIRMED – ENTRY COMPLETED")

        # (f) Verify a second participant's ticket can still be scanned and confirmed while first is blocked
        reg2_status, reg2_res, _ = http_json_request(
            "/api/register",
            "POST",
            {
                "name": "Second Alumni Scanner Test",
                "place": "Manjeri",
                "batchYear": "2018",
                "whatsappNumber": "9847011223",
                "participation": "പങ്കെടുക്കും",
            },
        )
        self.assertEqual(reg2_status, 200)
        second_id = reg2_res["registrationId"]
        second_token = reg2_res["ticketToken"]
        ver_other_status, ver_other_body, _ = http_json_request(
            "/api/admin/checkin/verify",
            "POST",
            {"qrData": second_token},
            headers=auth_headers,
        )
        self.assertEqual(ver_other_status, 200)
        self.assertEqual(ver_other_body.get("status"), "VALID_PENDING")
        # Clean up second test record
        http_json_request("/api/admin/delete", "POST", {"registrationId": second_id}, headers=auth_headers)

        # (g) Verify Check-in Report Excel (.xlsx) export endpoint works
        xlsx_req = urllib.request.Request(
            f"{BASE_URL}/api/admin/checkin/export-xlsx",
            headers=auth_headers,
            method="GET",
        )
        with urllib.request.urlopen(xlsx_req, timeout=5) as xlsx_resp:
            self.assertEqual(xlsx_resp.status, 200)
            self.assertIn("spreadsheetml.sheet", xlsx_resp.headers.get("Content-Type", ""))
            xlsx_bytes = xlsx_resp.read()
            self.assertTrue(xlsx_bytes.startswith(b"PK"))

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

        # 5A. Verify initial whatsappSent is False, then mark as sent via /api/admin/whatsapp-status
        self.assertFalse(reg_res["data"].get("whatsappSent", True))
        wa_status, wa_body, _ = http_json_request(
            "/api/admin/whatsapp-status",
            "POST",
            {"registrationId": created_id, "whatsappSent": True},
            headers=auth_headers,
        )
        self.assertEqual(wa_status, 200)
        self.assertTrue(wa_body.get("success"))
        self.assertTrue(wa_body["updatedRecord"]["whatsappSent"])
        self.assertEqual(wa_body["updatedRecord"]["whatsappSentCount"], 1)

        # Reminder send increments count while keeping whatsappSent True
        wa_status2, wa_body2, _ = http_json_request(
            "/api/admin/whatsapp-status",
            "POST",
            {"registrationId": created_id, "whatsappSent": True},
            headers=auth_headers,
        )
        self.assertEqual(wa_status2, 200)
        self.assertTrue(wa_body2["updatedRecord"]["whatsappSent"])
        self.assertEqual(wa_body2["updatedRecord"]["whatsappSentCount"], 2)

        # 5B. Edit the registration via /api/admin/update and confirm whatsappSent is preserved
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
        self.assertFalse(upd_body["updatedRecord"]["hasTicket"])
        self.assertEqual(upd_body["updatedRecord"]["ticketId"], "")
        self.assertEqual(upd_body["updatedRecord"]["ticketToken"], "")
        self.assertEqual(upd_body["updatedRecord"]["qrMatrix"], [])
        self.assertFalse(upd_body["updatedRecord"]["checkedIn"])
        self.assertEqual(upd_body["updatedRecord"]["checkInStatus"], "NOT ELIGIBLE")
        self.assertTrue(upd_body["updatedRecord"]["whatsappSent"])
        self.assertEqual(upd_body["updatedRecord"]["whatsappSentCount"], 2)

        # 5B-2. Direct Non-Attending ("സാധിക്കില്ല") Registration Enforcement Test
        no_status, no_res, _ = http_json_request(
            "/api/register",
            "POST",
            {
                "name": "Temp Alumni Unable",
                "place": "Manjeri",
                "batchYear": "2017",
                "whatsappNumber": "9847055667",
                "participation": "സാധിക്കില്ല",
            },
        )
        self.assertEqual(no_status, 200)
        self.assertTrue(no_res.get("success"))
        self.assertFalse(no_res.get("hasTicket", True))
        self.assertFalse(no_res.get("ticketEligible", True))
        self.assertEqual(no_res.get("ticketId"), "")
        self.assertEqual(no_res.get("ticketToken"), "")
        self.assertEqual(no_res.get("qrMatrix"), [])
        self.assertIn("REGISTRATION SUCCESSFUL!", no_res.get("confirmationMessage", ""))
        self.assertIn("We hope to meet you at another event!", no_res.get("confirmationMessage", ""))
        no_reg_id = no_res["registrationId"]

        # Public/Admin ticket lookup & QR check-in verification/confirm must deny non-attending registrations
        t_no_status, _, _ = http_json_request(f"/api/ticket?id={no_reg_id}", "GET", headers=auth_headers)
        self.assertEqual(t_no_status, 404)

        v_no_status, v_no_body, _ = http_json_request(
            "/api/admin/checkin/verify",
            "POST",
            {"qrData": no_reg_id, "allowIdLookup": True},
            headers=auth_headers,
        )
        self.assertEqual(v_no_status, 200)
        self.assertFalse(v_no_body.get("valid", True))
        self.assertTrue(v_no_body.get("notAttending"))
        self.assertEqual(v_no_body.get("status"), "INVALID")

        c_no_status, c_no_body, _ = http_json_request(
            "/api/admin/checkin/confirm",
            "POST",
            {"registrationId": no_reg_id},
            headers=auth_headers,
        )
        self.assertEqual(c_no_status, 403)
        self.assertFalse(c_no_body.get("success", True))
        self.assertTrue(c_no_body.get("notAttending"))

        http_json_request("/api/admin/delete", "POST", {"registrationId": no_reg_id}, headers=auth_headers)

        # 5C. Delete the registration via /api/admin/delete
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

        # Static Open Graph preview image & fonts must load with HTTP 200 and sensitive files must NOT be publicly served
        with urllib.request.urlopen(f"{BASE_URL}/aufbruch-og-preview.jpg", timeout=5) as resp:
            self.assertEqual(resp.status, 200)
            self.assertIn("image/jpeg", resp.headers.get("Content-Type", ""))
            self.assertGreater(len(resp.read()), 10000)

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

    def test_vercel_blob_storage_and_revocation(self):
        class FakeBlobNotFound(FileNotFoundError):
            pass

        class FakeGetResult:
            def __init__(self, body: bytes):
                self.body = body

        blob_store = {}

        class FakeBlobSync:
            BlobNotFoundError = FakeBlobNotFound

            @staticmethod
            def get_blob(pathname: str, access: str = "private"):
                self.assertEqual(access, "private")
                if pathname not in blob_store:
                    raise FakeBlobNotFound(pathname)
                return FakeGetResult(blob_store[pathname])

            @staticmethod
            def put_blob(pathname: str, body: bytes, access: str = "private", **kwargs):
                self.assertEqual(access, "private")
                self.assertTrue(kwargs.get("allow_overwrite"))
                self.assertFalse(kwargs.get("add_random_suffix", True))
                blob_store[pathname] = body

        import server
        orig_blob = server.vercel_blob
        orig_token = os.environ.get("BLOB_READ_WRITE_TOKEN")
        orig_revoked = set(server.REVOKED_TOKENS)
        try:
            server.vercel_blob = FakeBlobSync
            os.environ["BLOB_READ_WRITE_TOKEN"] = "vercel_blob_rw_test_token"
            self.assertEqual(server.get_storage_mode(), "vercel-blob")

            seeded = server.load_db()
            self.assertGreater(len(seeded), 0)
            self.assertIn(server.BLOB_RECORDS_PATH, blob_store)

            # Verify token revocation persists to private blob store
            tok = server.create_session("admin")
            verified = server._verify_signed_token(tok)
            self.assertIsNotNone(verified)
            server.revoke_session(tok)
            server.REVOKED_TOKENS.clear()
            self.assertIsNone(server._verify_signed_token(tok))

            # Verify uncached ?cache=0 delivery URL resolution when stream_blob exists
            FakeBlobSync.stream_blob = staticmethod(lambda *a, **kw: None)
            os.environ["BLOB_READ_WRITE_TOKEN"] = "vercel_blob_rw_abc123store_secretpart"
            self.assertEqual(
                server._blob_uncached_target(server.BLOB_RECORDS_PATH),
                f"https://abc123store.private.blob.vercel-storage.com/{server.BLOB_RECORDS_PATH}?cache=0",
            )
            delattr(FakeBlobSync, "stream_blob")
        finally:
            server.vercel_blob = orig_blob
            server.REVOKED_TOKENS.clear()
            server.REVOKED_TOKENS.update(orig_revoked)
            if orig_token is None:
                os.environ.pop("BLOB_READ_WRITE_TOKEN", None)
            else:
                os.environ["BLOB_READ_WRITE_TOKEN"] = orig_token

    def test_qr_matrix_iso_compliance_and_cloud_api_delivery(self):
        import qrcode
        import qrcode.util
        import server

        # 1. Verify /vendor/jsQR.js is served cleanly with 200 OK
        with urllib.request.urlopen(f"{BASE_URL}/vendor/jsQR.js", timeout=5) as resp:
            self.assertEqual(resp.status, 200)
            self.assertGreater(len(resp.read()), 100000)

        # 2. Verify make_qr_matrix generates 100% ISO-compliant finder separators & data bits
        for ver, sample in [
            (1, "AUF26-001"),
            (2, "AUF26-ANWAR001-7578BC76EB87"),
            (3, "AUF26-" + "A" * 38),
            (4, "AUF26-" + "B" * 64),
        ]:
            qr = qrcode.QRCode(
                version=ver,
                error_correction=qrcode.constants.ERROR_CORRECT_L,
                box_size=1,
                border=0,
                mask_pattern=0,
            )
            qr.add_data(qrcode.util.QRData(sample.encode("utf-8"), mode=qrcode.util.MODE_8BIT_BYTE))
            qr.make(fit=False)
            ref_mat = [[1 if c else 0 for c in row] for row in qr.get_matrix()]
            srv_mat = server.make_qr_matrix(sample)
            self.assertEqual(srv_mat, ref_mat, f"QR mismatch on version {ver}")

        # 3. Verify WhatsApp Business Cloud API payload formatting & failure isolation
        msg_text = server.build_checkin_whatsapp_message("Test Alumni", "2020", "ANWAR 007")
        self.assertIn("🛎️ *TICKET CONFIRMED...!*", msg_text)
        self.assertIn("Assalamu Alaikum,\n*Test Alumni*", msg_text)
        self.assertIn("Your Entry for *AUFBRUCH ALUMNI CONCLAVE 2026* has been Successfully Confirmed. 🤝", msg_text)
        self.assertIn("*Ticket Details:*", msg_text)
        self.assertIn("- Name: Test Alumni", msg_text)
        self.assertIn("- Batch: 2020", msg_text)
        self.assertIn("- Ticket ID: ANWAR 007", msg_text)
        self.assertIn("- Status: CONFIRMED ✅", msg_text)
        self.assertIn("*Majmau Ssaqafathil Islamiyya*\nDa'wa College Alumni", msg_text)

        orig_wa_tok = os.environ.get("WHATSAPP_CLOUD_API_TOKEN")
        orig_wa_pid = os.environ.get("WHATSAPP_PHONE_NUMBER_ID")
        orig_urlopen = server.urllib.request.urlopen
        try:
            os.environ["WHATSAPP_CLOUD_API_TOKEN"] = "test_token_123"
            os.environ["WHATSAPP_PHONE_NUMBER_ID"] = "1234567890"
            captured = {}

            class MockResp:
                status = 200

                def __enter__(self):
                    return self

                def __exit__(self, *args):
                    return False

                def read(self):
                    return json.dumps({"messages": [{"id": "wamid.TEST_CONFIRM_999"}]}).encode("utf-8")

            def fake_urlopen(req, timeout=10):
                captured["url"] = req.full_url
                captured["auth"] = req.headers.get("Authorization")
                captured["body"] = json.loads(req.data.decode("utf-8"))
                return MockResp()

            server.urllib.request.urlopen = fake_urlopen
            res_ok = server.send_whatsapp_cloud_api_message("9876543210", msg_text)
            self.assertTrue(res_ok.get("sent"))
            self.assertEqual(res_ok.get("messageId"), "wamid.TEST_CONFIRM_999")
            self.assertEqual(captured["body"]["to"], "919876543210")
            self.assertEqual(captured["auth"], "Bearer test_token_123")
        finally:
            server.urllib.request.urlopen = orig_urlopen
            if orig_wa_tok is None:
                os.environ.pop("WHATSAPP_CLOUD_API_TOKEN", None)
            else:
                os.environ["WHATSAPP_CLOUD_API_TOKEN"] = orig_wa_tok
            if orig_wa_pid is None:
                os.environ.pop("WHATSAPP_PHONE_NUMBER_ID", None)
            else:
                os.environ["WHATSAPP_PHONE_NUMBER_ID"] = orig_wa_pid


if __name__ == "__main__":
    unittest.main(verbosity=2)
