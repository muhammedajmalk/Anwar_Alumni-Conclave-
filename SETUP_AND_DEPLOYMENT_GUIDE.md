# Aufbruch – Alumni Conclave 2026
## Complete Website, Google Form Registration System, WhatsApp Automation & Admin Dashboard

### 1. Event Overview & Official Specifications
- **Event Title:** Aufbruch – Alumni Conclave 2026
- **Designed by:** Ajmal Kattichira

---

### 2. Project Deliverables in Workspace
| File | Description |
| :--- | :--- |
| [`public/index.html`](./public/index.html) | Complete, responsive, executive-level website & Google Apps Script Web App (`HtmlService`) in Deep Navy & Royal Gold. Includes: Hero Banner with live countdown, Conclave Schedule, the exact 5-field Registration Form, Post-Submission Confirmation Screen, Interactive Admin Dashboard (KPI cards, Attendance Donut, Batch-wise & Place-wise Charts, Searchable Responses Table, View/Edit/Delete/Send Message Modals, CSV Export), and Backend/Google Sheets Sync. |
| [`Code.gs`](./Code.gs) | Complete Google Apps Script backend: Account ownership guard (`anwarmajmau01@gmail.com`), automated Google Form builder (`createAufbruchGoogleForm`), Google Spreadsheet & Dashboard generator (`buildRegistrationDashboard`), `onFormSubmit` trigger handler, Indian mobile number validator, Malayalam WhatsApp Click-to-Chat URL builder, optional Meta WhatsApp Business Cloud API sender, Web App JSON/HTML endpoints (`doGet`, `doPost`, `submitRegistrationFromWebApp`, `getDashboardDataFromWebApp`), and end-to-end verification tests. |
| [`appsscript.json`](./appsscript.json) | Google Apps Script project manifest (`Asia/Kolkata` timezone and required OAuth scopes for Forms, Sheets, Drive, ScriptApp Triggers, External Requests, and User Email verification). |
| [`aufbruch_2026_form_header.png`](./aufbruch_2026_form_header.png) | Custom 1600×400 (4:1 aspect ratio) Deep Navy & Gold Header Banner for the native Google Form theme. |
| [`test_registration_system.py`](./test_registration_system.py) | Automated verification test suite validating Indian mobile number formats, Malayalam WhatsApp message generation, `സാധിക്കില്ല` suppression rules, and `Code.gs` / `Index.html` integrity. |

---

### 3. Step-by-Step Google Account Authorization & Deployment (`anwarmajmau01@gmail.com`)

> **IMPORTANT OWNERSHIP REQUIREMENT:**  
> All Google Forms, Google Sheets, triggers, and Apps Script automations must be created and owned exclusively by **`anwarmajmau01@gmail.com`**. `Code.gs` enforces `verifyAccountOwnership()`, which checks the active Google session email and blocks creation if any other account is signed in.

#### Step 1: Create the Project under `anwarmajmau01@gmail.com`
1. Sign in to [Google Apps Script](https://script.google.com/) strictly using **`anwarmajmau01@gmail.com`**.
2. Click **New project** and title it:  
   `Aufbruch – Alumni Conclave 2026 Registration System`
3. In `Code.gs`, replace the default code with the full contents of [`Code.gs`](./Code.gs).
4. Click **`+` (Add a file)** → **HTML**, name the file **`Index`** (Apps Script automatically appends `.html`), and paste the full contents of [`public/index.html`](./public/index.html).

#### Step 2: Run `setupAufbruchSystem()` & Authorize
1. Select **`setupAufbruchSystem`** in the function dropdown at the top of the Apps Script editor and click **Run**.
2. Complete the Google OAuth consent screen using **`anwarmajmau01@gmail.com`** (**Review permissions** → select `anwarmajmau01@gmail.com` → **Advanced** → **Allow**).
3. `setupAufbruchSystem()` will automatically create and configure in `anwarmajmau01@gmail.com`'s Google Drive:
   - **Google Form:** `Aufbruch – Alumni Conclave 2026` with the exact 5 required fields, Indian phone regex validation, and exact confirmation message.
   - **Google Spreadsheet:** `Aufbruch – Alumni Conclave 2026 – Registration Database` linked to the Form.
   - **Formatted `Form Responses 1` Tab:** Includes Timestamp, Name, Place, Batch Year, WhatsApp Number, Participation Choice (`പങ്കെടുക്കും` / `സാധിക്കില്ല`), Registration ID (`AUF-2026-XXXX`), Formatted `+91` Phone, Personalized Malayalam Message, and a clickable `📲 Send WhatsApp to {Name}` hyperlink formula.
   - **`Registration Dashboard` Tab:** Includes live KPI cards (Total Registrations, Participating, Not Participating, Confirmation Rate), Batch-wise & Place-wise tables, and 3 embedded charts (Attendance Pie Chart, Batch-wise Column Chart, Place-wise Bar Chart).
   - **Installable Triggers:** `onFormSubmit` and `onOpen` under `anwarmajmau01@gmail.com`.

#### Step 3: Deploy the Complete Website as a Google Web App
1. In the Apps Script editor, click **Deploy** → **New deployment** → select **Web app**.
2. Set **Execute as:** `Me (anwarmajmau01@gmail.com)` and **Who has access:** `Anyone`.
3. Click **Deploy** and copy the **Web App URL**.
4. You can also run locally via `python server.py` (serves `public/index.html` + `/api/*` on port `8765`), or deploy directly to **Vercel** (uses `vercel.json` + `public/` + `api/index.py`).

### 3A. Vercel Deployment Settings & Environment Variables
- **Framework Preset:** `Other` (`"framework": null` in `vercel.json`)
- **Build Command:** Leave empty (none required)
- **Output Directory:** `public` (`"outputDirectory": "public"` in `vercel.json`)
- **Recommended Vercel Environment Variables (Project Settings → Environment Variables):**
  - `ADMIN_USERNAME` — Administrator login username (defaults to `admin`)
  - `ADMIN_PASSWORD` — Administrator login password (set securely in Vercel)
  - `SESSION_SECRET` — Secret key used to sign HMAC admin session tokens
  - `BLOB_READ_WRITE_TOKEN` (Vercel Private Blob Store) — Automatically attached when a private Vercel Blob store is linked; provides durable cloud database and session-revocation storage across serverless instances
  - `KV_REST_API_URL` and `KV_REST_API_TOKEN` (Upstash / Vercel Redis REST) — Optional alternative durable KV persistence (falls back to bundled `registrations_db.json` -> `/tmp` when neither Blob nor KV is configured)
  - `GAS_WEBAPP_URL` — Optional Google Apps Script Web App `/exec` URL to mirror submissions to Google Sheets

---

### 4. WhatsApp Automation & Delivery Policy

#### Primary Workflow: Personalized WhatsApp Click-to-Chat (`wa.me`)
When a participant submits the form with **`പങ്കെടുക്കും`**:
- Their Indian phone number (with or without `+91`) is validated and normalized to `91XXXXXXXXXX`.
- The exact personalized Malayalam message is generated:
  ```text
  അസ്സലാമു അലൈകും

  Hi...🖐️ {Name}

  നിങ്ങൾ അൻവാർ അലുംനി കോൺക്ലൈവിൽ രജിസ്റ്റർ ചെയ്തതിന് നന്ദി...

  ഡിസംബർ 10 വൈകിട്ട് 3:30 മുതൽ രാത്രി 9:30 വരെ നടക്കുന്ന സംഗമത്തിൽ പങ്കാളിത്തം ഉറപ്പ് വരുത്തുക.
  ```
- The confirmation screen displays the **"📲 Send WhatsApp Confirmation"** button and launches `https://wa.me/91XXXXXXXXXX?text=...` with the recipient's number and pre-filled message.
- If the respondent selects **`സാധിക്കില്ല`**, WhatsApp link generation and sending are strictly suppressed both on the website and in Google Sheets.

#### Optional Direct Background Sending: WhatsApp Business Cloud API
Standard Google Forms `onFormSubmit` triggers run on Google servers and cannot silently control a user's personal WhatsApp app. If silent server-to-user messaging is desired:
1. Obtain a **Phone Number ID** and **Access Token** from the Meta Developer Portal (WhatsApp Business Cloud API).
2. Run `configureWhatsAppCloudApi('YOUR_PHONE_NUMBER_ID', 'YOUR_ACCESS_TOKEN', true)` in `Code.gs`.
3. **Truthfulness Guarantee:** `Code.gs` never claims a WhatsApp message was delivered unless the Meta Graph API returns HTTP 200 with a verified `messages[0].id` (`wamid`).
