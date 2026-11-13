/**
 * ============================================================================
 * PROJECT: AUFBRUCH – ALUMNI CONCLAVE 2026
 * Google Form Registration System with WhatsApp Automation & Analytics Dashboard
 * ============================================================================
 *
 * Event Title : Aufbruch – Alumni Conclave 2026
 * Date        : Thursday, December 10, 2026
 * Venue       : Majmau Academy, Nilambur
 * Event Time  : 3:30 PM to 9:30 PM
 * Owner       : anwarmajmau01@gmail.com
 *
 * Architecture:
 * 1. Google Account Ownership Guard (strictly enforces anwarmajmau01@gmail.com)
 * 2. Automated Google Form creation with exact field order & regex validation
 * 3. Automated Google Spreadsheet creation & destination linking
 * 4. Installable onFormSubmit trigger for real-time response processing
 * 5. Personalized Malayalam WhatsApp Click-to-Chat URL generator (wa.me)
 *    - Strictly skips users who select "സാധിക്കില്ല"
 * 6. Optional WhatsApp Business Cloud API integration (Meta Graph API)
 *    - Never claims delivery unless confirmed by HTTP 200 + message ID
 * 7. Executive Registration Dashboard with KPI cards, Batch/Place tables & Charts
 * 8. Custom Branded Web App (HtmlService) providing a Post-Submission
 *    "Send WhatsApp Confirmation" button linked directly to the Google Form
 * ============================================================================
 */

var CONFIG = {
  REQUIRED_OWNER_EMAIL: 'anwarmajmau01@gmail.com',
  ENFORCE_OWNER_CHECK: true,

  EVENT: {
    TITLE: 'Aufbruch – Alumni Conclave 2026',
    DATE: 'Thursday, December 10, 2026',
    VENUE: 'Majmau Academy, Nilambur',
    TIME: '3:30 PM to 9:30 PM',
    DESCRIPTION:
      'Welcome to the official registration portal for Aufbruch – Alumni Conclave 2026.\n\n' +
      '📅 Date: Thursday, December 10, 2026\n' +
      '🕒 Time: 3:30 PM to 9:30 PM\n' +
      '📍 Venue: Majmau Academy, Nilambur\n\n' +
      'Please complete the form below to confirm your registration.'
  },

  CONFIRMATION_MESSAGE:
    'Registration Successful!\n\n' +
    'Thank you for registering for Aufbruch – Alumni Conclave 2026.',

  FIELDS: {
    NAME: 'Name',
    PLACE: 'Place',
    BATCH_YEAR: 'Batch Year',
    WHATSAPP: 'WhatsApp Number',
    PARTICIPATION: 'അലുംനി സംഗമത്തിൽ പങ്കെടുക്കുമോ...?'
  },

  PARTICIPATION_OPTIONS: {
    YES: 'പങ്കെടുക്കും',
    NO: 'സാധിക്കില്ല'
  },

  SHEETS: {
    RESPONSES: 'Form Responses 1',
    DASHBOARD: 'Registration Dashboard',
    LOGS: 'System Logs'
  },

  COLORS: {
    NAVY_DARK: '#0A1628',
    NAVY_PRIMARY: '#122645',
    NAVY_LIGHT: '#1E3A5F',
    GOLD_ACCENT: '#D4AF37',
    GOLD_LIGHT: '#F9F3DF',
    WHITE: '#FFFFFF',
    BG_SOFT: '#F4F6F9',
    TEXT_DARK: '#1A202C',
    TEXT_MUTED: '#4A5568',
    SUCCESS_BG: '#DEF7EC',
    SUCCESS_TEXT: '#03543F',
    DECLINE_BG: '#FDE8E8',
    DECLINE_TEXT: '#9B1C1C'
  }
};

/**
 * ============================================================================
 * 1. GOOGLE ACCOUNT OWNERSHIP VERIFICATION
 * ============================================================================
 * Ensures that the entire system is created and owned exclusively by
 * anwarmajmau01@gmail.com.
 */
function verifyAccountOwnership() {
  var activeEmail = '';
  var effectiveEmail = '';

  try {
    activeEmail = (Session.getActiveUser().getEmail() || '').trim().toLowerCase();
  } catch (e) {
    Logger.log('Warning reading active user email: ' + e.message);
  }

  try {
    effectiveEmail = (Session.getEffectiveUser().getEmail() || '').trim().toLowerCase();
  } catch (e) {
    Logger.log('Warning reading effective user email: ' + e.message);
  }

  var requiredEmail = CONFIG.REQUIRED_OWNER_EMAIL.toLowerCase();
  var currentEmail = effectiveEmail || activeEmail;

  if (CONFIG.ENFORCE_OWNER_CHECK && currentEmail !== requiredEmail) {
    var errorMsg =
      'ACCOUNT OWNERSHIP MISMATCH!\n' +
      'Required Google Account : ' + CONFIG.REQUIRED_OWNER_EMAIL + '\n' +
      'Current Logged-In Account: ' + (currentEmail || 'Unknown / Unauthorized') + '\n\n' +
      'Action Required: Please sign in to ' + CONFIG.REQUIRED_OWNER_EMAIL +
      ' before running setupAufbruchSystem(). Creation aborted to protect ownership.';
    Logger.log(errorMsg);
    throw new Error(errorMsg);
  }

  Logger.log('Account ownership verified: ' + currentEmail);
  return currentEmail;
}

/**
 * ============================================================================
 * 2. MASTER SETUP & DEPLOYMENT FUNCTION
 * ============================================================================
 * Run this function once in the Google Apps Script editor after signing in as
 * anwarmajmau01@gmail.com to create the Form, Spreadsheet, Dashboard, and
 * onFormSubmit automation trigger.
 */
function setupAufbruchSystem() {
  // Step 1: Strictly verify that anwarmajmau01@gmail.com is the active owner
  var verifiedOwner = verifyAccountOwnership();

  var props = PropertiesService.getScriptProperties();
  var existingFormId = props.getProperty('FORM_ID');
  var existingSheetId = props.getProperty('SPREADSHEET_ID');

  var ss = null;
  var form = null;

  // Reuse existing setup if already created under this project, otherwise create fresh
  if (existingSheetId && existingFormId) {
    try {
      ss = SpreadsheetApp.openById(existingSheetId);
      form = FormApp.openById(existingFormId);
      Logger.log('Existing Form and Spreadsheet found. Updating configuration...');
    } catch (e) {
      ss = null;
      form = null;
    }
  }

  // Step 2: Create the Google Spreadsheet
  if (!ss) {
    ss = SpreadsheetApp.create(CONFIG.EVENT.TITLE + ' – Registration Database');
    props.setProperty('SPREADSHEET_ID', ss.getId());
    Logger.log('Created Google Spreadsheet: ' + ss.getUrl());
  }

  // Step 3: Create and configure the Google Form
  if (!form) {
    form = createAufbruchGoogleForm(ss);
    props.setProperty('FORM_ID', form.getId());
    Logger.log('Created Google Form: ' + form.getPublishedUrl());
  } else {
    configureExistingGoogleForm(form, ss);
  }

  // Step 4: Wait briefly for Google Forms to initialize the 'Form Responses 1' tab
  SpreadsheetApp.flush();
  Utilities.sleep(1500);

  // Step 5: Format the Form Responses sheet & add automation headers
  var responsesSheet = initializeResponsesSheet(ss);

  // Step 6: Build the Registration Management Dashboard & Audit Log sheet
  initializeSystemLogsSheet(ss);
  buildRegistrationDashboard(ss);

  // Step 7: Install the onFormSubmit trigger & custom spreadsheet menu
  installAutomationTriggers(ss);

  // Step 8: Store system metadata
  var deploymentResult = {
    ownerAccount: verifiedOwner,
    eventTitle: CONFIG.EVENT.TITLE,
    formId: form.getId(),
    formEditUrl: form.getEditUrl(),
    formPublishedUrl: form.getPublishedUrl(),
     formShortUrl: form.shortenFormUrl(form.getPublishedUrl()),
    spreadsheetId: ss.getId(),
    spreadsheetUrl: ss.getUrl(),
    responsesSheetName: responsesSheet.getName(),
    createdAt: new Date().toISOString()
  };

  props.setProperty('DEPLOYMENT_METADATA', JSON.stringify(deploymentResult));
  logSystemEvent(ss, 'SYSTEM_SETUP', 'SUCCESS', 'Aufbruch 2026 Registration System initialized by ' + verifiedOwner, JSON.stringify(deploymentResult));

  Logger.log('============================================================');
  Logger.log('AUFBRUCH – ALUMNI CONCLAVE 2026 SETUP COMPLETE');
  Logger.log('Owner Account     : ' + deploymentResult.ownerAccount);
  Logger.log('Google Form (Live): ' + deploymentResult.formPublishedUrl);
  Logger.log('Google Form (Edit): ' + deploymentResult.formEditUrl);
  Logger.log('Google Spreadsheet: ' + deploymentResult.spreadsheetUrl);
  Logger.log('============================================================');

  return deploymentResult;
}

/**
 * ============================================================================
 * 3. GOOGLE FORM CREATION & VALIDATION
 * ============================================================================
 */
function createAufbruchGoogleForm(ss) {
  var form = FormApp.create(CONFIG.EVENT.TITLE);
  configureExistingGoogleForm(form, ss);
  return form;
}

function configureExistingGoogleForm(form, ss) {
  form.setTitle(CONFIG.EVENT.TITLE);
  form.setDescription(CONFIG.EVENT.DESCRIPTION);
  form.setConfirmationMessage(CONFIG.CONFIRMATION_MESSAGE);
  form.setCollectEmail(false);
  form.setAllowResponseEdits(false);
  form.setShowLinkToRespondAgain(true);
  form.setPublishingSummary(false);

  // Clear existing items if re-running setup to prevent duplicate fields
  var existingItems = form.getItems();
  for (var i = existingItems.length - 1; i >= 0; i--) {
    form.deleteItem(existingItems[i]);
  }

  // 1. Name (Short Answer, Required)
  var nameItem = form.addTextItem();
  nameItem.setTitle(CONFIG.FIELDS.NAME)
    .setHelpText('Enter your full name')
    .setRequired(true);
  var nameValidation = FormApp.createTextValidation()
    .setHelpText('Please enter your full name (minimum 2 characters).')
    .requireTextMatchesPattern('^\\s*\\S.{1,99}$')
    .build();
  nameItem.setValidation(nameValidation);

  // 2. Place (Short Answer, Required)
  var placeItem = form.addTextItem();
  placeItem.setTitle(CONFIG.FIELDS.PLACE)
    .setHelpText('Enter your locality')
    .setRequired(true);
  var placeValidation = FormApp.createTextValidation()
    .setHelpText('Please enter a valid place name.')
    .requireTextMatchesPattern('^\\s*\\S.{1,99}$')
    .build();
  placeItem.setValidation(placeValidation);

  // 3. Batch Year (Short Answer, Required)
  var batchItem = form.addTextItem();
  batchItem.setTitle(CONFIG.FIELDS.BATCH_YEAR)
    .setHelpText('Enter your batch year')
    .setRequired(true);
  var batchValidation = FormApp.createTextValidation()
    .setHelpText('Please enter a valid 4-digit Batch Year (e.g., 2018).')
    .requireTextMatchesPattern('^\\s*(19[5-9]\\d|20[0-2]\\d)(\\s*[-–/]\\s*(19[5-9]\\d|20[0-2]\\d|\\d{2}))?\\s*$')
    .build();
  batchItem.setValidation(batchValidation);

  // 4. WhatsApp Number (Short Answer, Required, mobile validation with or without +91)
  var phoneItem = form.addTextItem();
  phoneItem.setTitle(CONFIG.FIELDS.WHATSAPP)
    .setHelpText('Mobile numbers with or without +91 country code')
    .setRequired(true);
  var phoneValidation = FormApp.createTextValidation()
    .setHelpText('Please enter a valid 10-digit mobile number.')
    .requireTextMatchesPattern('^\\s*(\\+91[\\-\\s]?|91[\\-\\s]?|0)?[6-9]\\d{4}[\\-\\s]?\\d{5}\\s*$')
    .build();
  phoneItem.setValidation(phoneValidation);

  // 5. അലുംനി സംഗമത്തിൽ പങ്കെടുക്കുമോ...? (Multiple Choice, Required)
  var participationItem = form.addMultipleChoiceItem();
  participationItem.setTitle(CONFIG.FIELDS.PARTICIPATION)
    .setRequired(true)
    .setChoices([
      participationItem.createChoice(CONFIG.PARTICIPATION_OPTIONS.YES),
      participationItem.createChoice(CONFIG.PARTICIPATION_OPTIONS.NO)
    ]);

  // Link the Google Form to the Google Spreadsheet
  if (ss) {
    try {
      form.setDestination(FormApp.DestinationType.SPREADSHEET, ss.getId());
    } catch (err) {
      Logger.log('Destination already linked or warning: ' + err.message);
    }
  }

  return form;
}

/**
 * ============================================================================
 * 4. SPREADSHEET INITIALIZATION & FORMATTING
 * ============================================================================
 */
function findOrCreateResponsesSheet(ss) {
  var sheets = ss.getSheets();
  for (var i = 0; i < sheets.length; i++) {
    var name = sheets[i].getName();
    if (name.indexOf('Form Responses') === 0 || name === CONFIG.SHEETS.RESPONSES) {
      if (name !== CONFIG.SHEETS.RESPONSES) {
        sheets[i].setName(CONFIG.SHEETS.RESPONSES);
      }
      return sheets[i];
    }
  }

  // Fallback if Form hasn't created the tab yet
  var sheet = ss.getSheetByName('Sheet1');
  if (sheet) {
    sheet.setName(CONFIG.SHEETS.RESPONSES);
    return sheet;
  }
  return ss.insertSheet(CONFIG.SHEETS.RESPONSES);
}

function initializeResponsesSheet(ss) {
  var sheet = findOrCreateResponsesSheet(ss);

  // Remove default empty Sheet1 if another Form Responses sheet was created
  var defaultSheet = ss.getSheetByName('Sheet1');
  if (defaultSheet && defaultSheet.getSheetId() !== sheet.getSheetId() && ss.getSheets().length > 1) {
    try {
      ss.deleteSheet(defaultSheet);
    } catch (e) {}
  }

  var headers = [
    'Timestamp',
    CONFIG.FIELDS.NAME,
    CONFIG.FIELDS.PLACE,
    CONFIG.FIELDS.BATCH_YEAR,
    CONFIG.FIELDS.WHATSAPP,
    CONFIG.FIELDS.PARTICIPATION,
    'Registration ID',
    'Formatted WhatsApp (+91)',
    'Attendance Status',
    'Personalized WhatsApp Message',
    'WhatsApp Click-to-Chat Action',
    'WhatsApp Status',
    'Processed Timestamp'
  ];

  var headerRange = sheet.getRange(1, 1, 1, headers.length);
  headerRange.setValues([headers]);
  headerRange
    .setBackground(CONFIG.COLORS.NAVY_DARK)
    .setFontColor(CONFIG.COLORS.GOLD_ACCENT)
    .setFontFamily('Arial')
    .setFontSize(10)
    .setFontWeight('bold')
    .setHorizontalAlignment('center')
    .setVerticalAlignment('middle')
    .setWrap(true);

  sheet.setRowHeight(1, 38);
  sheet.setFrozenRows(1);

  // Set clean column widths for easy reading and export
  var columnWidths = [155, 180, 150, 110, 150, 230, 140, 160, 145, 290, 220, 175, 155];
  for (var c = 0; c < columnWidths.length; c++) {
    sheet.setColumnWidth(c + 1, columnWidths[c]);
  }

  // Apply conditional formatting on Participation column (Column F = 6)
  var rules = [];
  var participationRange = sheet.getRange('F2:F1000');

  var yesRule = SpreadsheetApp.newConditionalFormatRule()
    .whenTextEqualTo(CONFIG.PARTICIPATION_OPTIONS.YES)
    .setBackground(CONFIG.COLORS.SUCCESS_BG)
    .setFontColor(CONFIG.COLORS.SUCCESS_TEXT)
    .setBold(true)
    .setRanges([participationRange])
    .build();

  var noRule = SpreadsheetApp.newConditionalFormatRule()
    .whenTextEqualTo(CONFIG.PARTICIPATION_OPTIONS.NO)
    .setBackground(CONFIG.COLORS.DECLINE_BG)
    .setFontColor(CONFIG.COLORS.DECLINE_TEXT)
    .setBold(true)
    .setRanges([participationRange])
    .build();

  rules.push(yesRule, noRule);
  sheet.setConditionalFormatRules(rules);

  return sheet;
}

/**
 * ============================================================================
 * 5. INDIAN PHONE VALIDATION & WHATSAPP CLICK-TO-CHAT GENERATOR
 * ============================================================================
 */
/**
 * Validates and normalizes an Indian mobile number.
 * Accepts:
 *   - 9876543210
 *   - +919876543210
 *   - +91 98765 43210
 *   - +91-9876543210
 *   - 919876543210
 *   - 09876543210
 * Returns:
 *   {
 *     isValid: boolean,
 *     nationalNumber: '9876543210',
 *     waNumber: '919876543210',       // Used for https://wa.me/919876543210
 *     e164: '+919876543210',          // Standard E.164 format
 *     display: '+91 98765 43210',     // Human-friendly display
 *     error: string|null
 *   }
 */
function normalizeIndianPhoneNumber(rawInput) {
  if (rawInput === null || rawInput === undefined) {
    return { isValid: false, error: 'Phone number is required.' };
  }

  var str = String(rawInput).trim();
  // Strip spaces, hyphens, dots, parentheses
  var cleaned = str.replace(/[\s\-\.\(\)]/g, '');

  // Remove leading +91, 91 (when 12 digits), or 0 (when 11 digits)
  var national = cleaned;
  if (national.indexOf('+91') === 0) {
    national = national.substring(3);
  } else if (national.length === 12 && national.indexOf('91') === 0) {
    national = national.substring(2);
  } else if (national.length === 11 && national.indexOf('0') === 0) {
    national = national.substring(1);
  }

  // Validate 10-digit Indian mobile number starting with 6, 7, 8, or 9
  if (!/^[6-9]\d{9}$/.test(national)) {
    return {
      isValid: false,
      raw: str,
      error: 'Invalid Indian mobile number. Must be a 10-digit number starting with 6, 7, 8, or 9 (with or without +91).'
    };
  }

  var waNumber = '91' + national;
  var e164 = '+91' + national;
  var display = '+91 ' + national.substring(0, 5) + ' ' + national.substring(5);

  return {
    isValid: true,
    nationalNumber: national,
    waNumber: waNumber,
    e164: e164,
    display: display,
    error: null
  };
}

/**
 * Generates the exact personalized Malayalam WhatsApp message required for
 * Aufbruch – Alumni Conclave 2026.
 */
function buildWhatsAppMessage(name) {
  var cleanName = String(name || 'Alumni Member').trim();
  return (
    'അസ്സലാമു അലൈകും\n\n' +
    'Hi... *' + cleanName + '*\n\n' +
    'നിങ്ങൾ അൻവാർ അലുംനി കോൺക്ലൈവിൽ രജിസ്റ്റർ ചെയ്തതിന് നന്ദി...\n\n' +
    '*ഡിസംബർ 10 വൈകിട്ട് 3:30 മുതൽ രാത്രി 9:30 വരെ* നടക്കുന്ന സംഗമത്തിൽ പങ്കാളിത്തം ഉറപ്പ് വരുത്തുക.'
  );
}

/**
 * Generates the WhatsApp Click-to-Chat URL and message ONLY if the participant
 * selected "പങ്കെടുക്കും". Strictly suppresses generation if "സാധിക്കില്ല" is selected.
 */
function generateWhatsAppConfirmationData(name, rawPhone, participationChoice) {
  var choice = String(participationChoice || '').trim();

  // Rule: Do NOT send messages or generate links for users who selected "സാധിക്കില്ല"
  if (choice === CONFIG.PARTICIPATION_OPTIONS.NO || choice !== CONFIG.PARTICIPATION_OPTIONS.YES) {
    return {
      shouldSend: false,
      reason: 'Participant selected "' + (choice || 'സാധിക്കില്ല') + '" (Not Participating). WhatsApp message suppressed.',
      phoneData: normalizeIndianPhoneNumber(rawPhone),
      message: '',
      clickToChatUrl: '',
      apiUrl: ''
    };
  }

  var phoneData = normalizeIndianPhoneNumber(rawPhone);
  if (!phoneData.isValid) {
    return {
      shouldSend: false,
      reason: 'Invalid WhatsApp Number: ' + phoneData.error,
      phoneData: phoneData,
      message: '',
      clickToChatUrl: '',
      apiUrl: ''
    };
  }

  var message = buildWhatsAppMessage(name);
  var encodedText = encodeURIComponent(message);

  // Official WhatsApp Click-to-Chat URLs formatted with country code 91
  var clickToChatUrl = 'https://wa.me/' + phoneData.waNumber + '?text=' + encodedText;
  var apiUrl = 'https://api.whatsapp.com/send?phone=' + phoneData.waNumber + '&text=' + encodedText;

  return {
    shouldSend: true,
    reason: 'Ready for WhatsApp confirmation',
    phoneData: phoneData,
    message: message,
    clickToChatUrl: clickToChatUrl,
    apiUrl: apiUrl
  };
}

/**
 * ============================================================================
 * 6. OPTIONAL WHATSAPP BUSINESS CLOUD API INTEGRATION (META GRAPH API)
 * ============================================================================
 * NOTE: Standard Google Forms triggers cannot silently control a user's personal
 * WhatsApp app. For silent background sending, Meta's official WhatsApp Business
 * Cloud API is supported below when WHATSAPP_CLOUD_API_ENABLED = 'true' and valid
 * WHATSAPP_ACCESS_TOKEN and WHATSAPP_PHONE_NUMBER_ID are configured in ScriptProperties.
 *
 * CRITICAL GUARANTEE: This function NEVER claims a WhatsApp message was sent unless
 * the Meta Graph API returns HTTP 200 and a valid 'messages[0].id' (wamid).
 */
function sendWhatsAppViaCloudApiIfConfigured(waNumber, messageText) {
  var props = PropertiesService.getScriptProperties();
  var enabled = props.getProperty('WHATSAPP_CLOUD_API_ENABLED') === 'true';
  var accessToken = props.getProperty('WHATSAPP_ACCESS_TOKEN');
  var phoneNumberId = props.getProperty('WHATSAPP_PHONE_NUMBER_ID');

  if (!enabled || !accessToken || !phoneNumberId) {
    return {
      attempted: false,
      delivered: false,
      statusText: 'Click-to-Chat Link Ready (Manual / One-Click Send)',
      messageId: null
    };
  }

  var endpoint = 'https://graph.facebook.com/v21.0/' + encodeURIComponent(phoneNumberId) + '/messages';
  var payload = {
    messaging_product: 'whatsapp',
    recipient_type: 'individual',
    to: waNumber,
    type: 'text',
    text: {
      preview_url: false,
      body: messageText
    }
  };

  try {
    var response = UrlFetchApp.fetch(endpoint, {
      method: 'post',
      contentType: 'application/json',
      headers: {
        Authorization: 'Bearer ' + accessToken
      },
      payload: JSON.stringify(payload),
      muteHttpExceptions: true
    });

    var statusCode = response.getResponseCode();
    var bodyText = response.getContentText();
    var parsed = JSON.parse(bodyText || '{}');

    if (statusCode >= 200 && statusCode < 300 && parsed.messages && parsed.messages[0] && parsed.messages[0].id) {
      var wamid = parsed.messages[0].id;
      return {
        attempted: true,
        delivered: true,
        statusText: 'Sent via Cloud API (' + wamid + ')',
        messageId: wamid
      };
    } else {
      var apiErr = (parsed.error && parsed.error.message) ? parsed.error.message : ('HTTP ' + statusCode);
      return {
        attempted: true,
        delivered: false,
        statusText: 'Cloud API Failed (' + apiErr + ') – Use Click-to-Chat Link',
        messageId: null
      };
    }
  } catch (err) {
    return {
      attempted: true,
      delivered: false,
      statusText: 'Cloud API Exception (' + err.message + ') – Use Click-to-Chat Link',
      messageId: null
    };
  }
}

/**
 * Helper to configure optional WhatsApp Business Cloud API credentials.
 */
function configureWhatsAppCloudApi(phoneNumberId, accessToken, enableSending) {
  verifyAccountOwnership();
  var props = PropertiesService.getScriptProperties();
  props.setProperty('WHATSAPP_PHONE_NUMBER_ID', String(phoneNumberId || '').trim());
  props.setProperty('WHATSAPP_ACCESS_TOKEN', String(accessToken || '').trim());
  props.setProperty('WHATSAPP_CLOUD_API_ENABLED', enableSending ? 'true' : 'false');
  Logger.log('WhatsApp Business Cloud API configuration updated. Enabled: ' + Boolean(enableSending));
}

/**
 * ============================================================================
 * 7. FORM SUBMISSION TRIGGER HANDLER (onFormSubmit)
 * ============================================================================
 */
function onFormSubmit(e) {
  var lock = LockService.getScriptLock();
  lock.waitLock(30000);

  try {
    var ss = null;
    if (e && e.range && e.range.getSheet) {
      ss = e.range.getSheet().getParent();
    } else {
      var sheetId = PropertiesService.getScriptProperties().getProperty('SPREADSHEET_ID');
      ss = sheetId ? SpreadsheetApp.openById(sheetId) : SpreadsheetApp.getActiveSpreadsheet();
    }

    var sheet = initializeResponsesSheet(ss);
    var targetRow = (e && e.range) ? e.range.getRow() : sheet.getLastRow();

    if (targetRow <= 1) {
      return;
    }

    var result = processRegistrationRow(ss, sheet, targetRow);
    updateDashboardTablesAndCharts(ss);

    return result;
  } catch (err) {
    Logger.log('Error in onFormSubmit: ' + err.stack);
    try {
      var fallbackSheetId = PropertiesService.getScriptProperties().getProperty('SPREADSHEET_ID');
      if (fallbackSheetId) {
        logSystemEvent(SpreadsheetApp.openById(fallbackSheetId), 'ON_FORM_SUBMIT_ERROR', 'ERROR', err.message, err.stack || '');
      }
    } catch (innerErr) {}
    throw err;
  } finally {
    lock.releaseLock();
  }
}

/**
 * Processes a specific registration row in 'Form Responses 1' idempotently.
 */
function processRegistrationRow(ss, sheet, rowNumber) {
  var rowValues = sheet.getRange(rowNumber, 1, 1, 13).getValues()[0];

  var timestamp = rowValues[0] || new Date();
  var name = String(rowValues[1] || '').trim();
  var place = String(rowValues[2] || '').trim();
  var batchYear = String(rowValues[3] || '').trim();
  var rawPhone = String(rowValues[4] || '').trim();
  var participation = String(rowValues[5] || '').trim();
  var existingRegId = String(rowValues[6] || '').trim();

  // Generate sequential Registration ID (e.g., 001)
  var regNumber = rowNumber - 1;
  var regId = existingRegId || ('000' + regNumber).slice(-3);

  var waData = generateWhatsAppConfirmationData(name, rawPhone, participation);
  var formattedPhone = waData.phoneData && waData.phoneData.isValid
    ? waData.phoneData.display
    : ('INVALID: ' + rawPhone);

  var attendanceStatus = (participation === CONFIG.PARTICIPATION_OPTIONS.YES)
    ? 'Participating (പങ്കെടുക്കും)'
    : 'Not Participating (സാധിക്കില്ല)';

  var personalizedMessage = '';
  var deliveryStatus = '';
  var processedTimestamp = Utilities.formatDate(new Date(), Session.getScriptTimeZone() || 'Asia/Kolkata', 'yyyy-MM-dd HH:mm:ss');

  // Normalize Batch Year and Place in the sheet for clean grouping
  if (name) sheet.getRange(rowNumber, 2).setValue(name);
  if (place) sheet.getRange(rowNumber, 3).setValue(toTitleCase(place));
  if (batchYear) sheet.getRange(rowNumber, 4).setValue(batchYear);

  if (waData.shouldSend) {
    personalizedMessage = waData.message;

    // Optional Cloud API call if enabled; otherwise sets status to Link Ready
    var apiOutcome = sendWhatsAppViaCloudApiIfConfigured(waData.phoneData.waNumber, waData.message);
    deliveryStatus = apiOutcome.statusText;

    // Write values to columns G..M (columns 7..13)
    sheet.getRange(rowNumber, 7).setValue(regId);
    sheet.getRange(rowNumber, 8).setValue(formattedPhone);
    sheet.getRange(rowNumber, 9).setValue(attendanceStatus);
    sheet.getRange(rowNumber, 10).setValue(personalizedMessage);

    // Column K (11): Clickable HYPERLINK formula for instant WhatsApp Click-to-Chat
    var safeUrl = waData.clickToChatUrl.replace(/"/g, '""');
    var safeLabel = ('📲 Send WhatsApp to ' + name).replace(/"/g, '""');
    sheet.getRange(rowNumber, 11)
      .setFormula('=HYPERLINK("' + safeUrl + '", "' + safeLabel + '")')
      .setFontColor('#075E54')
      .setFontWeight('bold');

    sheet.getRange(rowNumber, 12).setValue(deliveryStatus);
    sheet.getRange(rowNumber, 13).setValue(processedTimestamp);

    logSystemEvent(
      ss,
      'REGISTRATION_PROCESSED',
      'SUCCESS',
      'Registered ' + name + ' (' + regId + ') – Participating',
      JSON.stringify({
        regId: regId,
        name: name,
        place: place,
        batchYear: batchYear,
        phone: waData.phoneData.e164,
        clickToChatUrl: waData.clickToChatUrl,
        deliveryStatus: deliveryStatus
      })
    );
  } else {
    // User selected "സാധിക്കില്ല" OR phone number was invalid
    personalizedMessage = (participation === CONFIG.PARTICIPATION_OPTIONS.NO)
      ? 'N/A – Do Not Send (Selected സാധിക്കില്ല)'
      : ('Blocked: ' + waData.reason);

    deliveryStatus = (participation === CONFIG.PARTICIPATION_OPTIONS.NO)
      ? 'Skipped – Not Participating (സാധിക്കില്ല)'
      : 'Validation Error – Phone Invalid';

    sheet.getRange(rowNumber, 7).setValue(regId);
    sheet.getRange(rowNumber, 8).setValue(formattedPhone);
    sheet.getRange(rowNumber, 9).setValue(attendanceStatus);
    sheet.getRange(rowNumber, 10).setValue(personalizedMessage);
    sheet.getRange(rowNumber, 11)
      .setValue('🚫 No WhatsApp Sent (സാധിക്കില്ല)')
      .setFontColor(CONFIG.COLORS.DECLINE_TEXT)
      .setFontWeight('normal');
    sheet.getRange(rowNumber, 12).setValue(deliveryStatus);
    sheet.getRange(rowNumber, 13).setValue(processedTimestamp);

    logSystemEvent(
      ss,
      'REGISTRATION_PROCESSED',
      'SKIPPED_WHATSAPP',
      'Registered ' + name + ' (' + regId + ') – ' + waData.reason,
      JSON.stringify({
        regId: regId,
        name: name,
        participation: participation,
        reason: waData.reason
      })
    );
  }

  // Format row alignment cleanly
  sheet.getRange(rowNumber, 1, 1, 13).setVerticalAlignment('middle');
  sheet.getRange(rowNumber, 4).setHorizontalAlignment('center');
  sheet.getRange(rowNumber, 6, 1, 4).setHorizontalAlignment('center');

  return {
    regId: regId,
    rowNumber: rowNumber,
    name: name,
    place: place,
    batchYear: batchYear,
    participation: participation,
    whatsapp: waData
  };
}

/**
 * ============================================================================
 * 8. REGISTRATION MANAGEMENT DASHBOARD & CHARTS
 * ============================================================================
 */
function buildRegistrationDashboard(ss) {
  var dash = ss.getSheetByName(CONFIG.SHEETS.DASHBOARD);
  if (!dash) {
    dash = ss.insertSheet(CONFIG.SHEETS.DASHBOARD, 0);
  } else {
    dash.clear();
    var existingCharts = dash.getCharts();
    for (var i = 0; i < existingCharts.length; i++) {
      dash.removeChart(existingCharts[i]);
    }
  }

  dash.setHiddenGridlines(true);

  // Set column widths for clean layout
  var colWidths = [30, 220, 140, 140, 40, 220, 140, 140, 30];
  for (var c = 0; c < colWidths.length; c++) {
    dash.setColumnWidth(c + 1, colWidths[c]);
  }

  // Banner Header (Rows 2-3, Columns B-H)
  dash.getRange('B2:H2').merge()
    .setValue('AUFBRUCH – ALUMNI CONCLAVE 2026 | REGISTRATION DASHBOARD')
    .setBackground(CONFIG.COLORS.NAVY_DARK)
    .setFontColor(CONFIG.COLORS.GOLD_ACCENT)
    .setFontFamily('Arial')
    .setFontSize(15)
    .setFontWeight('bold')
    .setHorizontalAlignment('center')
    .setVerticalAlignment('middle');
  dash.setRowHeight(2, 42);

  dash.getRange('B3:H3').merge()
    .setValue('📅 Thursday, December 10, 2026   •   🕒 3:30 PM to 9:30 PM   •   📍 Majmau Academy, Nilambur')
    .setBackground(CONFIG.COLORS.NAVY_PRIMARY)
    .setFontColor(CONFIG.COLORS.WHITE)
    .setFontFamily('Arial')
    .setFontSize(10)
    .setFontWeight('bold')
    .setHorizontalAlignment('center')
    .setVerticalAlignment('middle');
  dash.setRowHeight(3, 28);

  // KPI Summary Cards Header (Row 5) & Live Formulas (Row 6)
  // Card 1: Total Registrations (B5:C6)
  dash.getRange('B5:C5').merge()
    .setValue('TOTAL REGISTRATIONS')
    .setBackground(CONFIG.COLORS.NAVY_LIGHT)
    .setFontColor(CONFIG.COLORS.WHITE)
    .setFontWeight('bold')
    .setFontSize(9)
    .setHorizontalAlignment('center');
  dash.getRange('B6:C6').merge()
    .setFormula('=COUNTA(\'' + CONFIG.SHEETS.RESPONSES + '\'!B2:B)')
    .setBackground(CONFIG.COLORS.BG_SOFT)
    .setFontColor(CONFIG.COLORS.NAVY_DARK)
    .setFontWeight('bold')
    .setFontSize(22)
    .setHorizontalAlignment('center')
    .setVerticalAlignment('middle');

  // Card 2: Participating Members (D5:D6)
  dash.getRange('D5')
    .setValue('PARTICIPATING (പങ്കെടുക്കും)')
    .setBackground('#03543F')
    .setFontColor(CONFIG.COLORS.WHITE)
    .setFontWeight('bold')
    .setFontSize(9)
    .setHorizontalAlignment('center');
  dash.getRange('D6')
    .setFormula('=COUNTIF(\'' + CONFIG.SHEETS.RESPONSES + '\'!F2:F, "' + CONFIG.PARTICIPATION_OPTIONS.YES + '")')
    .setBackground(CONFIG.COLORS.SUCCESS_BG)
    .setFontColor(CONFIG.COLORS.SUCCESS_TEXT)
    .setFontWeight('bold')
    .setFontSize(22)
    .setHorizontalAlignment('center')
    .setVerticalAlignment('middle');

  // Card 3: Not Participating Members (F5:G6)
  dash.getRange('F5:G5').merge()
    .setValue('NOT PARTICIPATING (സാധിക്കില്ല)')
    .setBackground('#9B1C1C')
    .setFontColor(CONFIG.COLORS.WHITE)
    .setFontWeight('bold')
    .setFontSize(9)
    .setHorizontalAlignment('center');
  dash.getRange('F6:G6').merge()
    .setFormula('=COUNTIF(\'' + CONFIG.SHEETS.RESPONSES + '\'!F2:F, "' + CONFIG.PARTICIPATION_OPTIONS.NO + '")')
    .setBackground(CONFIG.COLORS.DECLINE_BG)
    .setFontColor(CONFIG.COLORS.DECLINE_TEXT)
    .setFontWeight('bold')
    .setFontSize(22)
    .setHorizontalAlignment('center')
    .setVerticalAlignment('middle');

  // Card 4: Participation Rate (H5:H6)
  dash.getRange('H5')
    .setValue('CONFIRMATION RATE')
    .setBackground(CONFIG.COLORS.NAVY_DARK)
    .setFontColor(CONFIG.COLORS.GOLD_ACCENT)
    .setFontWeight('bold')
    .setFontSize(9)
    .setHorizontalAlignment('center');
  dash.getRange('H6')
    .setFormula('=IF(B6>0, D6/B6, 0)')
    .setNumberFormat('0.0%')
    .setBackground(CONFIG.COLORS.GOLD_LIGHT)
    .setFontColor(CONFIG.COLORS.NAVY_DARK)
    .setFontWeight('bold')
    .setFontSize(20)
    .setHorizontalAlignment('center')
    .setVerticalAlignment('middle');

  dash.setRowHeight(5, 26);
  dash.setRowHeight(6, 52);

  // Attendance Summary Table for Pie Chart (Hidden / Compact Reference in B8:C10)
  dash.getRange('B8:D8').setValues([['Attendance Category', 'Member Count', 'Share (%)']])
    .setBackground(CONFIG.COLORS.NAVY_DARK)
    .setFontColor(CONFIG.COLORS.GOLD_ACCENT)
    .setFontWeight('bold')
    .setHorizontalAlignment('center');
  dash.getRange('B9').setValue('പങ്കെടുക്കും (Participating)');
  dash.getRange('C9').setFormula('=COUNTIF(\'' + CONFIG.SHEETS.RESPONSES + '\'!F2:F, "' + CONFIG.PARTICIPATION_OPTIONS.YES + '")');
  dash.getRange('D9').setFormula('=IF(B6>0, C9/B6, 0)').setNumberFormat('0.0%');

  dash.getRange('B10').setValue('സാധിക്കില്ല (Not Participating)');
  dash.getRange('C10').setFormula('=COUNTIF(\'' + CONFIG.SHEETS.RESPONSES + '\'!F2:F, "' + CONFIG.PARTICIPATION_OPTIONS.NO + '")');
  dash.getRange('D10').setFormula('=IF(B6>0, C10/B6, 0)').setNumberFormat('0.0%');
  dash.getRange('B8:D10').setBorder(true, true, true, true, true, true, '#CBD5E0', SpreadsheetApp.BorderStyle.SOLID);

  // Populate Batch-wise and Place-wise breakdown tables and charts
  updateDashboardTablesAndCharts(ss);

  return dash;
}

/**
 * Dynamically aggregates Batch-wise and Place-wise counts and refreshes embedded charts.
 */
function updateDashboardTablesAndCharts(ss) {
  var dash = ss.getSheetByName(CONFIG.SHEETS.DASHBOARD);
  var respSheet = ss.getSheetByName(CONFIG.SHEETS.RESPONSES);
  if (!dash || !respSheet) return;

  var lastRow = respSheet.getLastRow();
  var batchCounts = {};
  var placeCounts = {};

  if (lastRow >= 2) {
    var data = respSheet.getRange(2, 1, lastRow - 1, 6).getValues();
    for (var i = 0; i < data.length; i++) {
      var name = String(data[i][1] || '').trim();
      var place = toTitleCase(String(data[i][2] || '').trim()) || 'Unspecified';
      var batch = String(data[i][3] || '').trim() || 'Unspecified';
      var part = String(data[i][5] || '').trim();

      if (!name && !rawPhonePresent(data[i][4])) continue;

      if (!batchCounts[batch]) {
        batchCounts[batch] = { total: 0, yes: 0, no: 0 };
      }
      batchCounts[batch].total++;
      if (part === CONFIG.PARTICIPATION_OPTIONS.YES) batchCounts[batch].yes++;
      else batchCounts[batch].no++;

      if (!placeCounts[place]) {
        placeCounts[place] = { total: 0, yes: 0, no: 0 };
      }
      placeCounts[place].total++;
      if (part === CONFIG.PARTICIPATION_OPTIONS.YES) placeCounts[place].yes++;
      else placeCounts[place].no++;
    }
  }

  // Clear previous dynamic table area (Row 26 downwards)
  dash.getRange('B26:H100').clearContent().clearFormat();

  // Section Header: Batch-wise & Place-wise Tables (Row 26)
  dash.getRange('B26:D26').merge()
    .setValue('🎓 BATCH-WISE REGISTRATION COUNT')
    .setBackground(CONFIG.COLORS.NAVY_DARK)
    .setFontColor(CONFIG.COLORS.GOLD_ACCENT)
    .setFontWeight('bold')
    .setFontSize(11)
    .setHorizontalAlignment('center');

  dash.getRange('F26:H26').merge()
    .setValue('📍 PLACE-WISE REGISTRATION COUNT')
    .setBackground(CONFIG.COLORS.NAVY_DARK)
    .setFontColor(CONFIG.COLORS.GOLD_ACCENT)
    .setFontWeight('bold')
    .setFontSize(11)
    .setHorizontalAlignment('center');
  dash.setRowHeight(26, 30);

  // Table Subheaders (Row 27)
  dash.getRange('B27:D27').setValues([['Batch Year', 'Total Registered', 'Participating (പങ്കെടുക്കും)']])
    .setBackground(CONFIG.COLORS.NAVY_PRIMARY)
    .setFontColor(CONFIG.COLORS.WHITE)
    .setFontWeight('bold')
    .setHorizontalAlignment('center');

  dash.getRange('F27:H27').setValues([['Place / City', 'Total Registered', 'Participating (പങ്കെടുക്കും)']])
    .setBackground(CONFIG.COLORS.NAVY_PRIMARY)
    .setFontColor(CONFIG.COLORS.WHITE)
    .setFontWeight('bold')
    .setHorizontalAlignment('center');

  // Sort Batch keys chronologically
  var batchKeys = Object.keys(batchCounts).sort();
  var batchRows = [];
  if (batchKeys.length === 0) {
    batchRows.push(['No Registrations Yet', 0, 0]);
  } else {
    for (var b = 0; b < batchKeys.length; b++) {
      var bk = batchKeys[b];
      batchRows.push([bk, batchCounts[bk].total, batchCounts[bk].yes]);
    }
  }

  var batchTableRange = dash.getRange(28, 2, batchRows.length, 3);
  batchTableRange.setValues(batchRows)
    .setHorizontalAlignment('center')
    .setBorder(true, true, true, true, true, true, '#CBD5E0', SpreadsheetApp.BorderStyle.SOLID);

  // Sort Place keys by descending total count
  var placeKeys = Object.keys(placeCounts).sort(function(a, b) {
    return placeCounts[b].total - placeCounts[a].total;
  });
  var placeRows = [];
  if (placeKeys.length === 0) {
    placeRows.push(['No Registrations Yet', 0, 0]);
  } else {
    for (var p = 0; p < placeKeys.length; p++) {
      var pk = placeKeys[p];
      placeRows.push([pk, placeCounts[pk].total, placeCounts[pk].yes]);
    }
  }

  var placeTableRange = dash.getRange(28, 6, placeRows.length, 3);
  placeTableRange.setValues(placeRows)
    .setHorizontalAlignment('center')
    .setBorder(true, true, true, true, true, true, '#CBD5E0', SpreadsheetApp.BorderStyle.SOLID);

  // Rebuild Charts cleanly
  var existingCharts = dash.getCharts();
  for (var cIdx = 0; cIdx < existingCharts.length; cIdx++) {
    dash.removeChart(existingCharts[cIdx]);
  }

  // Chart 1: Attendance Breakdown Pie Chart (anchored at F8)
  var pieChart = dash.newChart()
    .setChartType(Charts.ChartType.PIE)
    .addRange(dash.getRange('B8:C10'))
    .setPosition(8, 6, 0, 0)
    .setOption('title', 'Attendance Confirmation Breakdown')
    .setOption('pieHole', 0.4)
    .setOption('width', 460)
    .setOption('height', 240)
    .setOption('colors', ['#0E9F6E', '#E02424'])
    .setOption('legend', { position: 'right' })
    .build();
  dash.insertChart(pieChart);

  // Chart 2: Batch-wise Registration Count Column Chart (anchored at B12)
  var batchChartEndRow = 27 + Math.max(1, batchRows.length);
  var batchChart = dash.newChart()
    .setChartType(Charts.ChartType.COLUMN)
    .addRange(dash.getRange('B27:C' + batchChartEndRow))
    .setPosition(12, 2, 0, 0)
    .setOption('title', 'Batch-wise Registration Count')
    .setOption('width', 460)
    .setOption('height', 230)
    .setOption('colors', [CONFIG.COLORS.NAVY_PRIMARY])
    .setOption('legend', { position: 'none' })
    .build();
  dash.insertChart(batchChart);

  // Chart 3: Place-wise Registration Count Bar Chart (anchored at F12)
  var placeChartEndRow = 27 + Math.max(1, placeRows.length);
  var placeChart = dash.newChart()
    .setChartType(Charts.ChartType.BAR)
    .addRange(dash.getRange('F27:G' + placeChartEndRow))
    .setPosition(12, 6, 0, 0)
    .setOption('title', 'Place-wise Registration Count')
    .setOption('width', 460)
    .setOption('height', 230)
    .setOption('colors', [CONFIG.COLORS.GOLD_ACCENT])
    .setOption('legend', { position: 'none' })
    .build();
  dash.insertChart(placeChart);
}

function rawPhonePresent(val) {
  return String(val || '').trim().length > 0;
}

function toTitleCase(str) {
  return String(str || '').replace(/\w\S*/g, function(txt) {
    return txt.charAt(0).toUpperCase() + txt.substr(1).toLowerCase();
  });
}

/**
 * ============================================================================
 * 9. AUDIT LOGGING & TRIGGER MANAGEMENT
 * ============================================================================
 */
function initializeSystemLogsSheet(ss) {
  var logSheet = ss.getSheetByName(CONFIG.SHEETS.LOGS);
  if (!logSheet) {
    logSheet = ss.insertSheet(CONFIG.SHEETS.LOGS);
  }

  if (logSheet.getLastRow() === 0) {
    var headers = ['Timestamp (IST)', 'Event Type', 'Status', 'Summary', 'Metadata JSON'];
    logSheet.getRange(1, 1, 1, headers.length)
      .setValues([headers])
      .setBackground(CONFIG.COLORS.NAVY_DARK)
      .setFontColor(CONFIG.COLORS.GOLD_ACCENT)
      .setFontWeight('bold');
    logSheet.setFrozenRows(1);
    logSheet.setColumnWidth(1, 165);
    logSheet.setColumnWidth(2, 180);
    logSheet.setColumnWidth(3, 130);
    logSheet.setColumnWidth(4, 340);
    logSheet.setColumnWidth(5, 420);
  }
  return logSheet;
}

function logSystemEvent(ss, eventType, status, summary, metadataJson) {
  try {
    var logSheet = initializeSystemLogsSheet(ss);
    var nowStr = Utilities.formatDate(new Date(), Session.getScriptTimeZone() || 'Asia/Kolkata', 'yyyy-MM-dd HH:mm:ss');
    logSheet.appendRow([nowStr, eventType, status, summary, metadataJson || '']);
  } catch (e) {
    Logger.log('Failed to write system log: ' + e.message);
  }
}

function installAutomationTriggers(ss) {
  var existingTriggers = ScriptApp.getProjectTriggers();
  for (var i = 0; i < existingTriggers.length; i++) {
    var handler = existingTriggers[i].getHandlerFunction();
    if (handler === 'onFormSubmit' || handler === 'onOpen') {
      ScriptApp.deleteTrigger(existingTriggers[i]);
    }
  }

  ScriptApp.newTrigger('onFormSubmit')
    .forSpreadsheet(ss)
    .onFormSubmit()
    .create();

  ScriptApp.newTrigger('onOpen')
    .forSpreadsheet(ss)
    .onOpen()
    .create();

  Logger.log('Installed onFormSubmit and onOpen triggers for Spreadsheet ID: ' + ss.getId());
}

/**
 * Adds a custom "Aufbruch 2026 Admin" menu inside the Google Spreadsheet.
 */
function onOpen() {
  try {
    var ui = SpreadsheetApp.getUi();
    ui.createMenu('🎓 Aufbruch 2026 Admin')
      .addItem('🔄 Refresh Registration Dashboard', 'manualRefreshDashboard')
      .addItem('⚡ Re-process All Pending Rows', 'reprocessAllRows')
      .addSeparator()
      .addItem('🧪 Run End-to-End Verification Tests', 'runEndToEndVerificationTests')
      .addItem('🧹 Remove Test Submissions', 'cleanupTestSubmissions')
      .addToUi();
  } catch (e) {}
}

function manualRefreshDashboard() {
  var sheetId = PropertiesService.getScriptProperties().getProperty('SPREADSHEET_ID');
  var ss = sheetId ? SpreadsheetApp.openById(sheetId) : SpreadsheetApp.getActiveSpreadsheet();
  updateDashboardTablesAndCharts(ss);
}

function reprocessAllRows() {
  var sheetId = PropertiesService.getScriptProperties().getProperty('SPREADSHEET_ID');
  var ss = sheetId ? SpreadsheetApp.openById(sheetId) : SpreadsheetApp.getActiveSpreadsheet();
  var sheet = initializeResponsesSheet(ss);
  var lastRow = sheet.getLastRow();
  for (var r = 2; r <= lastRow; r++) {
    processRegistrationRow(ss, sheet, r);
  }
  updateDashboardTablesAndCharts(ss);
}

/**
 * ============================================================================
 * 10. CUSTOM BRANDED EXECUTIVE WEB APP & BACKEND ADMIN AUTHENTICATION
 * ============================================================================
 * Serves the Deep Navy & Gold executive registration portal and post-submission
 * WhatsApp confirmation page, connected directly to the Google Form & Sheet.
 * Admin Dashboard routes are strictly protected on the backend via session tokens.
 */
var ADMIN_AUTH_SALT = 'aufbruch_2026_majmau_salt:';
// SHA-256 hex digest of 'aufbruch_2026_majmau_salt:Aufbruch@2026'
var DEFAULT_ADMIN_HASH = '72c7c2c4a1242006f10142eb225ef3e7c71f72b09072d81e80b8a83649e0f561';

function computeSaltedSha256Hex(rawPassword) {
  var digest = Utilities.computeDigest(
    Utilities.DigestAlgorithm.SHA_256,
    ADMIN_AUTH_SALT + String(rawPassword || ''),
    Utilities.Charset.UTF_8
  );
  var hex = '';
  for (var i = 0; i < digest.length; i++) {
    var b = (digest[i] < 0) ? (digest[i] + 256) : digest[i];
    var h = b.toString(16);
    hex += (h.length === 1 ? '0' + h : h);
  }
  return hex;
}

/**
 * Allows the administrator (anwarmajmau01@gmail.com) to update the admin
 * username and password hash stored in ScriptProperties.
 */
function configureAdminCredentials(username, password) {
  verifyAccountOwnership();
  var props = PropertiesService.getScriptProperties();
  props.setProperty('ADMIN_USERNAME', String(username || 'admin').trim());
  props.setProperty('ADMIN_PASSWORD_HASH', computeSaltedSha256Hex(password));
  Logger.log('Admin credentials updated in ScriptProperties.');
}

function authenticateAdminFromWebApp(username, password) {
  var props = PropertiesService.getScriptProperties();
  var expectedUser = props.getProperty('ADMIN_USERNAME') || 'admin';
  var expectedHash = props.getProperty('ADMIN_PASSWORD_HASH') || DEFAULT_ADMIN_HASH;

  var cleanUser = String(username || '').trim();
  var candidateHash = computeSaltedSha256Hex(password);

  if (cleanUser !== expectedUser || candidateHash !== expectedHash) {
    return {
      success: false,
      authenticated: false,
      error: 'Invalid administrator username or password.'
    };
  }

  var token = Utilities.getUuid() + '-' + Utilities.getUuid();
  var cache = CacheService.getScriptCache();
  cache.put('ADMIN_SESSION_' + token, cleanUser, 21600); // 6 hours

  return {
    success: true,
    authenticated: true,
    username: cleanUser,
    sessionToken: token
  };
}

function isValidAdminSessionToken(sessionToken) {
  var token = String(sessionToken || '').trim();
  if (!token) return false;
  var cache = CacheService.getScriptCache();
  var storedUser = cache.get('ADMIN_SESSION_' + token);
  return Boolean(storedUser);
}

function logoutAdminFromWebApp(sessionToken) {
  var token = String(sessionToken || '').trim();
  if (token) {
    CacheService.getScriptCache().remove('ADMIN_SESSION_' + token);
  }
  return { success: true, authenticated: false };
}

function doGet(e) {
  if (e && e.parameter && e.parameter.action === 'dashboard') {
    var token = e.parameter.sessionToken || '';
    var data = getDashboardDataFromWebApp(token);
    return ContentService.createTextOutput(JSON.stringify(data))
      .setMimeType(ContentService.MimeType.JSON);
  }

  var template = HtmlService.createTemplateFromFile('Index');
  var props = PropertiesService.getScriptProperties();
  var metadataStr = props.getProperty('DEPLOYMENT_METADATA') || '{}';
  template.deploymentMetadata = metadataStr;

  return template.evaluate()
    .setTitle('Aufbruch – Alumni Conclave 2026 | Official Registration & Executive Portal')
    .setXFrameOptionsMode(HtmlService.XFrameOptionsMode.ALLOWALL)
    .addMetaTag('viewport', 'width=device-width, initial-scale=1');
}

/**
 * Handles JSON POST requests from standalone or external deployments of the website.
 */
function doPost(e) {
  try {
    var body = (e && e.postData && e.postData.contents) ? JSON.parse(e.postData.contents) : {};
    var action = body.action || 'register';

    if (action === 'adminLogin') {
      var authRes = authenticateAdminFromWebApp(body.username, body.password);
      return ContentService.createTextOutput(JSON.stringify(authRes))
        .setMimeType(ContentService.MimeType.JSON);
    }

    if (action === 'adminLogout') {
      var outRes = logoutAdminFromWebApp(body.sessionToken);
      return ContentService.createTextOutput(JSON.stringify(outRes))
        .setMimeType(ContentService.MimeType.JSON);
    }

    if (action === 'dashboard') {
      var dashData = getDashboardDataFromWebApp(body.sessionToken);
      return ContentService.createTextOutput(JSON.stringify(dashData))
        .setMimeType(ContentService.MimeType.JSON);
    }

    if (action === 'adminUpdate') {
      var updateRes = updateRegistrationFromAdmin(body.sessionToken, body);
      return ContentService.createTextOutput(JSON.stringify(updateRes))
        .setMimeType(ContentService.MimeType.JSON);
    }

    if (action === 'adminDelete') {
      var deleteRes = deleteRegistrationFromAdmin(body.sessionToken, body.registrationId);
      return ContentService.createTextOutput(JSON.stringify(deleteRes))
        .setMimeType(ContentService.MimeType.JSON);
    }

    var result = submitRegistrationFromWebApp(body);
    return ContentService.createTextOutput(JSON.stringify(result))
      .setMimeType(ContentService.MimeType.JSON);
  } catch (err) {
    var errMsg = err && err.message ? err.message : 'Registration failed. Please try again.';
    return ContentService.createTextOutput(JSON.stringify({
      success: false,
      message: errMsg,
      error: errMsg
    })).setMimeType(ContentService.MimeType.JSON);
  }
}

/**
 * Returns live registration rows, KPI totals, Batch-wise counts, Place-wise counts,
 * and system metadata from Google Sheets for the Website Admin Dashboard.
 * Strictly requires a valid administrator session token.
 */
function getDashboardDataFromWebApp(sessionToken) {
  if (!isValidAdminSessionToken(sessionToken)) {
    return {
      success: false,
      authenticated: false,
      error: 'Unauthorized access. Valid administrator session required.'
    };
  }

  var props = PropertiesService.getScriptProperties();
  var sheetId = props.getProperty('SPREADSHEET_ID');
  var metadataStr = props.getProperty('DEPLOYMENT_METADATA') || '{}';
  var metadata = {};
  try {
    metadata = JSON.parse(metadataStr);
  } catch (e) {}

  if (!sheetId) {
    return {
      success: true,
      authenticated: true,
      initialized: false,
      ownerEmail: CONFIG.REQUIRED_OWNER_EMAIL,
      metadata: metadata,
      registrations: [],
      stats: { total: 0, participating: 0, notParticipating: 0, confirmationRate: 0 },
      batchBreakdown: [],
      placeBreakdown: []
    };
  }

  var ss = SpreadsheetApp.openById(sheetId);
  var sheet = initializeResponsesSheet(ss);
  var lastRow = sheet.getLastRow();
  var registrations = [];
  var total = 0;
  var participating = 0;
  var notParticipating = 0;
  var batchMap = {};
  var placeMap = {};

  if (lastRow >= 2) {
    var rows = sheet.getRange(2, 1, lastRow - 1, 13).getValues();
    for (var i = 0; i < rows.length; i++) {
      var r = rows[i];
      var name = String(r[1] || '').trim();
      var place = toTitleCase(String(r[2] || '').trim());
      var batchYear = String(r[3] || '').trim();
      var rawPhone = String(r[4] || '').trim();
      var participation = String(r[5] || '').trim();
      if (!name && !rawPhone) continue;

      var regId = String(r[6] || ('000' + (i + 1)).slice(-3)).trim();
      var waData = generateWhatsAppConfirmationData(name, rawPhone, participation);
      var ts = r[0] instanceof Date
        ? Utilities.formatDate(r[0], Session.getScriptTimeZone() || 'Asia/Kolkata', 'yyyy-MM-dd HH:mm:ss')
        : String(r[0] || '');

      total++;
      var isYes = (participation === CONFIG.PARTICIPATION_OPTIONS.YES);
      if (isYes) participating++;
      else notParticipating++;

      var bKey = batchYear || 'Unspecified';
      if (!batchMap[bKey]) batchMap[bKey] = { batchYear: bKey, total: 0, yes: 0, no: 0 };
      batchMap[bKey].total++;
      if (isYes) batchMap[bKey].yes++; else batchMap[bKey].no++;

      var pKey = place || 'Unspecified';
      if (!placeMap[pKey]) placeMap[pKey] = { place: pKey, total: 0, yes: 0, no: 0 };
      placeMap[pKey].total++;
      if (isYes) placeMap[pKey].yes++; else placeMap[pKey].no++;

      registrations.push({
        registrationId: regId,
        timestamp: ts,
        name: name,
        place: place,
        batchYear: batchYear,
        whatsappNumber: rawPhone,
        formattedPhone: waData.phoneData && waData.phoneData.isValid ? waData.phoneData.display : rawPhone,
        waNumber: waData.phoneData && waData.phoneData.isValid ? waData.phoneData.waNumber : '',
        participation: participation,
        shouldSendWhatsApp: waData.shouldSend,
        whatsAppMessage: waData.message,
        whatsAppClickToChatUrl: waData.clickToChatUrl,
        whatsappStatus: String(r[11] || (waData.shouldSend ? 'Click-to-Chat Ready' : 'Skipped (സാധിക്കില്ല)'))
      });
    }
  }

  registrations.reverse();

  var batchBreakdown = Object.keys(batchMap).sort().map(function(k) { return batchMap[k]; });
  var placeBreakdown = Object.keys(placeMap).sort(function(a, b) { return placeMap[b].total - placeMap[a].total; }).map(function(k) { return placeMap[k]; });

  return {
    success: true,
    authenticated: true,
    initialized: true,
    ownerEmail: CONFIG.REQUIRED_OWNER_EMAIL,
    metadata: metadata,
    registrations: registrations,
    stats: {
      total: total,
      participating: participating,
      notParticipating: notParticipating,
      confirmationRate: total > 0 ? Math.round((participating / total) * 1000) / 10 : 0
    },
    batchBreakdown: batchBreakdown,
    placeBreakdown: placeBreakdown
  };
}

/**
 * Updates an existing registration record in Google Sheets (Form Responses 1)
 * and refreshes the Google Sheets Registration Dashboard.
 * Strictly requires a valid administrator session token.
 */
function updateRegistrationFromAdmin(sessionToken, payload) {
  if (!isValidAdminSessionToken(sessionToken)) {
    throw new Error('Unauthorized access. Valid administrator session required.');
  }
  if (!payload || !payload.registrationId) {
    throw new Error('Registration ID is required for updating.');
  }

  var targetRegId = String(payload.registrationId || '').trim();
  var name = String(payload.name || '').trim();
  var place = String(payload.place || '').trim();
  var batchYear = String(payload.batchYear || '').trim();
  var whatsappNumber = String(payload.whatsappNumber || '').trim();
  var participation = String(payload.participation || '').trim();

  if (name.length < 2) {
    throw new Error('Please enter a valid full name (minimum 2 characters).');
  }
  if (place.length < 2) {
    throw new Error('Please enter a valid locality / place.');
  }
  if (!/^(19[5-9]\d|20[0-2]\d)(\s*[-–/]\s*(19[5-9]\d|20[0-2]\d|\d{2}))?$/.test(batchYear)) {
    throw new Error('Please enter a valid 4-digit Batch Year (e.g., 2018).');
  }
  var phoneCheck = normalizeIndianPhoneNumber(whatsappNumber);
  if (!phoneCheck.isValid) {
    throw new Error('Please enter a valid 10-digit mobile number.');
  }
  if (participation !== CONFIG.PARTICIPATION_OPTIONS.YES && participation !== CONFIG.PARTICIPATION_OPTIONS.NO) {
    throw new Error('Please select a valid Attendance Status (പങ്കെടുക്കും or സാധിക്കില്ല).');
  }

  var props = PropertiesService.getScriptProperties();
  var sheetId = props.getProperty('SPREADSHEET_ID');
  if (!sheetId) {
    throw new Error('Google Spreadsheet not initialized yet.');
  }

  var lock = LockService.getScriptLock();
  lock.waitLock(30000);
  try {
    var ss = SpreadsheetApp.openById(sheetId);
    var sheet = initializeResponsesSheet(ss);
    var lastRow = sheet.getLastRow();
    var targetRow = -1;

    if (lastRow >= 2) {
      var regIds = sheet.getRange(2, 7, lastRow - 1, 1).getValues();
      for (var i = 0; i < regIds.length; i++) {
        var rowRegId = String(regIds[i][0] || ('000' + (i + 1)).slice(-3)).trim();
        if (rowRegId === targetRegId) {
          targetRow = i + 2;
          break;
        }
      }
    }

    if (targetRow === -1) {
      throw new Error('Registration #' + targetRegId + ' not found in Google Sheets.');
    }

    // Update Columns B..G (Name, Place, Batch Year, WhatsApp Number, Participation, Registration ID)
    sheet.getRange(targetRow, 2, 1, 6).setValues([[
      name,
      toTitleCase(place),
      batchYear,
      whatsappNumber,
      participation,
      targetRegId
    ]]);

    // Re-run row processor to update formatted phone, attendance status, and WhatsApp Click-to-Chat link
    processRegistrationRow(ss, sheet, targetRow);
    updateDashboardTablesAndCharts(ss);
    logSystemEvent(ss, 'ADMIN_UPDATE_REGISTRATION', 'SUCCESS', 'Updated registration #' + targetRegId + ' (' + name + ')', JSON.stringify(payload));

    return getDashboardDataFromWebApp(sessionToken);
  } finally {
    lock.releaseLock();
  }
}

/**
 * Permanently deletes a registration record from Google Sheets (Form Responses 1)
 * and refreshes the Google Sheets Registration Dashboard.
 * Strictly requires a valid administrator session token.
 */
function deleteRegistrationFromAdmin(sessionToken, registrationId) {
  if (!isValidAdminSessionToken(sessionToken)) {
    throw new Error('Unauthorized access. Valid administrator session required.');
  }

  var targetRegId = String(registrationId || '').trim();
  if (!targetRegId) {
    throw new Error('Registration ID is required for deletion.');
  }

  var props = PropertiesService.getScriptProperties();
  var sheetId = props.getProperty('SPREADSHEET_ID');
  if (!sheetId) {
    throw new Error('Google Spreadsheet not initialized yet.');
  }

  var lock = LockService.getScriptLock();
  lock.waitLock(30000);
  try {
    var ss = SpreadsheetApp.openById(sheetId);
    var sheet = initializeResponsesSheet(ss);
    var lastRow = sheet.getLastRow();
    var targetRow = -1;

    if (lastRow >= 2) {
      var regIds = sheet.getRange(2, 7, lastRow - 1, 1).getValues();
      for (var i = 0; i < regIds.length; i++) {
        var rowRegId = String(regIds[i][0] || ('000' + (i + 1)).slice(-3)).trim();
        if (rowRegId === targetRegId) {
          targetRow = i + 2;
          break;
        }
      }
    }

    if (targetRow === -1) {
      throw new Error('Registration #' + targetRegId + ' not found in Google Sheets.');
    }

    sheet.deleteRow(targetRow);
    updateDashboardTablesAndCharts(ss);
    logSystemEvent(ss, 'ADMIN_DELETE_REGISTRATION', 'SUCCESS', 'Deleted registration #' + targetRegId, JSON.stringify({ deletedId: targetRegId }));

    return getDashboardDataFromWebApp(sessionToken);
  } finally {
    lock.releaseLock();
  }
}

/**
 * Receives a submission from the custom Web App, validates all fields, submits
 * the response directly to the official Google Form & linked Google Sheet,
 * and returns the confirmation message + personalized WhatsApp Click-to-Chat URL.
 */
function submitRegistrationFromWebApp(payload) {
  if (!payload) {
    throw new Error('Submission payload is empty.');
  }

  var name = String(payload.name || '').trim();
  var place = String(payload.place || '').trim();
  var batchYear = String(payload.batchYear || '').trim();
  var whatsappNumber = String(payload.whatsappNumber || '').trim();
  var participation = String(payload.participation || '').trim();

  // 1. Validate fields
  if (name.length < 2) {
    throw new Error('Please enter your full name.');
  }
  if (place.length < 2) {
    throw new Error('Please enter your Place.');
  }
  if (!/^(19[5-9]\d|20[0-2]\d)(\s*[-–/]\s*(19[5-9]\d|20[0-2]\d|\d{2}))?$/.test(batchYear)) {
    throw new Error('Please enter a valid 4-digit Batch Year (e.g., 2018).');
  }

  var phoneCheck = normalizeIndianPhoneNumber(whatsappNumber);
  if (!phoneCheck.isValid) {
    throw new Error(phoneCheck.error);
  }

  if (participation !== CONFIG.PARTICIPATION_OPTIONS.YES && participation !== CONFIG.PARTICIPATION_OPTIONS.NO) {
    throw new Error('Please select whether you will attend the Alumni Conclave.');
  }

  var props = PropertiesService.getScriptProperties();
  var formId = props.getProperty('FORM_ID');
  var sheetId = props.getProperty('SPREADSHEET_ID');

  if (!formId || !sheetId) {
    throw new Error('System not initialized yet. Please run setupAufbruchSystem() first.');
  }

  var lock = LockService.getScriptLock();
  lock.waitLock(30000);

  try {
    var form = FormApp.openById(formId);
    var ss = SpreadsheetApp.openById(sheetId);
    var sheet = initializeResponsesSheet(ss);

    // Submit directly to Google Form so both Form & Spreadsheet stay 100% in sync
    var items = form.getItems();
    var formResponse = form.createResponse();

    for (var i = 0; i < items.length; i++) {
      var item = items[i];
      var title = item.getTitle();
      if (title === CONFIG.FIELDS.NAME) {
        formResponse.withItemResponse(item.asTextItem().createResponse(name));
      } else if (title === CONFIG.FIELDS.PLACE) {
        formResponse.withItemResponse(item.asTextItem().createResponse(place));
      } else if (title === CONFIG.FIELDS.BATCH_YEAR) {
        formResponse.withItemResponse(item.asTextItem().createResponse(batchYear));
      } else if (title === CONFIG.FIELDS.WHATSAPP) {
        formResponse.withItemResponse(item.asTextItem().createResponse(whatsappNumber));
      } else if (title === CONFIG.FIELDS.PARTICIPATION) {
        formResponse.withItemResponse(item.asMultipleChoiceItem().createResponse(participation));
      }
    }

    formResponse.submit();
    SpreadsheetApp.flush();
    Utilities.sleep(800);

    var lastRow = sheet.getLastRow();
    var processed = processRegistrationRow(ss, sheet, lastRow);
    updateDashboardTablesAndCharts(ss);

    var recData = {
      registrationId: processed.regId,
      confirmationMessage: CONFIG.CONFIRMATION_MESSAGE,
      name: name,
      place: place,
      batchYear: batchYear,
      formattedPhone: phoneCheck.display,
      participation: participation,
      shouldSendWhatsApp: processed.whatsapp.shouldSend,
      whatsAppMessage: processed.whatsapp.message,
      whatsAppClickToChatUrl: processed.whatsapp.clickToChatUrl
    };

    return {
      success: true,
      message: 'Registration completed successfully',
      data: recData,
      registrationId: processed.regId,
      confirmationMessage: CONFIG.CONFIRMATION_MESSAGE,
      name: name,
      place: place,
      batchYear: batchYear,
      formattedPhone: phoneCheck.display,
      participation: participation,
      shouldSendWhatsApp: processed.whatsapp.shouldSend,
      whatsAppMessage: processed.whatsapp.message,
      whatsAppClickToChatUrl: processed.whatsapp.clickToChatUrl
    };
  } finally {
    lock.releaseLock();
  }
}

/**
 * ============================================================================
 * 11. END-TO-END AUTOMATED VERIFICATION TESTS
 * ============================================================================
 */
function runEndToEndVerificationTests() {
  Logger.log('Starting End-to-End Verification Tests for Aufbruch – Alumni Conclave 2026...');

  // Test 1: Phone Number Normalization & Validation
  var t1 = normalizeIndianPhoneNumber('9876543210');
  var t2 = normalizeIndianPhoneNumber('+91 98765 43210');
  var t3 = normalizeIndianPhoneNumber('+91-9876543210');
  var t4 = normalizeIndianPhoneNumber('09876543210');
  var t5 = normalizeIndianPhoneNumber('12345'); // Invalid

  if (!t1.isValid || t1.waNumber !== '919876543210') throw new Error('Test 1A failed');
  if (!t2.isValid || t2.waNumber !== '919876543210') throw new Error('Test 1B failed');
  if (!t3.isValid || t3.waNumber !== '919876543210') throw new Error('Test 1C failed');
  if (!t4.isValid || t4.waNumber !== '919876543210') throw new Error('Test 1D failed');
  if (t5.isValid) throw new Error('Test 1E failed: accepted invalid number');

  // Test 2: WhatsApp Message & URL Generation for Participating ("പങ്കെടുക്കും")
  var waYes = generateWhatsAppConfirmationData('Muhammed Anwar', '+91 9876543210', 'പങ്കെടുക്കും');
  if (!waYes.shouldSend || waYes.clickToChatUrl.indexOf('https://wa.me/919876543210?text=') !== 0) {
    throw new Error('Test 2 failed: Participating member did not get valid wa.me URL');
  }

  // Test 3: Strict Suppression for Non-Participating ("സാധിക്കില്ല")
  var waNo = generateWhatsAppConfirmationData('Abdul Rasheed', '9876543211', 'സാധിക്കില്ല');
  if (waNo.shouldSend || waNo.clickToChatUrl !== '') {
    throw new Error('Test 3 failed: Non-participating member ("സാധിക്കില്ല") should NOT generate a WhatsApp link');
  }

  // Test 4: Live Form & Spreadsheet Integration (if setupAufbruchSystem has been run)
  var props = PropertiesService.getScriptProperties();
  var formId = props.getProperty('FORM_ID');
  var sheetId = props.getProperty('SPREADSHEET_ID');

  var liveSubmissionResults = [];
  if (formId && sheetId) {
    var sub1 = submitRegistrationFromWebApp({
      name: '[TEST] Muhammed Anwar',
      place: 'Nilambur',
      batchYear: '2016',
      whatsappNumber: '+91 9876543210',
      participation: 'പങ്കെടുക്കും'
    });
    var sub2 = submitRegistrationFromWebApp({
      name: '[TEST] Salman Faris',
      place: 'Manjeri',
      batchYear: '2018',
      whatsappNumber: '9876543211',
      participation: 'സാധിക്കില്ല'
    });
    liveSubmissionResults.push(sub1, sub2);
  }

  var summary = {
    phoneValidationPassed: true,
    participatingWhatsAppLinkPassed: true,
    nonParticipatingSuppressionPassed: true,
    liveSubmissionsTested: liveSubmissionResults.length,
    liveSubmissionResults: liveSubmissionResults
  };

  Logger.log('ALL END-TO-END VERIFICATION TESTS PASSED:\n' + JSON.stringify(summary, null, 2));
  return summary;
}

/**
 * Removes rows created by runEndToEndVerificationTests() where Name starts with '[TEST]'.
 */
function cleanupTestSubmissions() {
  var sheetId = PropertiesService.getScriptProperties().getProperty('SPREADSHEET_ID');
  if (!sheetId) return;
  var ss = SpreadsheetApp.openById(sheetId);
  var sheet = initializeResponsesSheet(ss);
  var lastRow = sheet.getLastRow();

  for (var r = lastRow; r >= 2; r--) {
    var nameVal = String(sheet.getRange(r, 2).getValue() || '');
    if (nameVal.indexOf('[TEST]') === 0) {
      sheet.deleteRow(r);
    }
  }
  updateDashboardTablesAndCharts(ss);
  Logger.log('Cleaned up test submissions.');
}
