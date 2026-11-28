// Marathi strings for shared controls that every portal's topbar renders —
// notifications, theme, language, navigation (merged into MR in ../i18n-mr.ts).
export const MR_SHARED: Record<string, string> = {
  // ── Topbar: notifications, theme, language, navigation ──
  Notifications: "सूचना",
  "{n} unread notification": "{n} न वाचलेली सूचना",
  "{n} unread notifications": "{n} न वाचलेल्या सूचना",
  "Mark all read": "सर्व वाचल्या म्हणून खूण करा",
  "You're all caught up.": "सर्व सूचना पाहून झाल्या.",
  "Switch to light mode": "लाइट मोड वापरा",
  "Switch to dark mode": "डार्क मोड वापरा",
  "Toggle dark mode": "डार्क मोड बदला",
  "Open navigation": "मेनू उघडा",
  "Close navigation": "मेनू बंद करा",
  Language: "भाषा",

  // ── Mail viewer (components/EmailHtmlView) ──
  "Show full email": "संपूर्ण ईमेल दाखवा",

  // ── Error messages (translateError in ../i18n.tsx) ──
  // Request never reached the server, and one plain line per HTTP status.
  "Could not reach the server. Check your connection and try again.":
    "सर्व्हरशी संपर्क होऊ शकला नाही. इंटरनेट कनेक्शन तपासून पुन्हा प्रयत्न करा.",
  "The request was not accepted.": "विनंती स्वीकारली गेली नाही.",
  "Please sign in again.": "कृपया पुन्हा साइन इन करा.",
  "You do not have permission for this.": "यासाठी तुम्हाला परवानगी नाही.",
  "Not found.": "सापडले नाही.",
  "This conflicts with a recent change. Refresh and try again.":
    "हे नुकत्याच झालेल्या बदलाशी जुळत नाही. पेज रिफ्रेश करून पुन्हा प्रयत्न करा.",
  "The file is too large.": "फाइल खूप मोठी आहे.",
  "Some details are missing or not valid.": "काही माहिती अपूर्ण किंवा चुकीची आहे.",
  "Too many requests. Please wait a moment and try again.":
    "खूप जास्त विनंत्या आल्या. थोडा वेळ थांबून पुन्हा प्रयत्न करा.",
  "Something went wrong on the server. Please try again.": "सर्व्हरवर काहीतरी चूक झाली. कृपया पुन्हा प्रयत्न करा.",
  "The server could not complete the request. Please try again.":
    "सर्व्हर विनंती पूर्ण करू शकला नाही. कृपया पुन्हा प्रयत्न करा.",
  "This service is not available right now. Please try again later.":
    "ही सेवा सध्या उपलब्ध नाही. कृपया नंतर पुन्हा प्रयत्न करा.",
  "The server took too long to respond. Please try again.":
    "सर्व्हरने उत्तर द्यायला खूप वेळ घेतला. कृपया पुन्हा प्रयत्न करा.",
  "Request failed ({code}).": "विनंती अयशस्वी झाली ({code}).",

  // Messages the server sends to supplier accounts (backend routers/portal, po_ack, auth, attachments).
  "PO reference not found for your account": "तुमच्या खात्यासाठी हा PO संदर्भ सापडला नाही",
  "PO not found for your account": "तुमच्या खात्यासाठी हा PO सापडला नाही",
  "ASN not found": "ASN सापडला नाही",
  "Attachment not found": "जोडलेली फाइल सापडली नाही",
  "Could not fetch the file from storage": "स्टोरेजमधून फाइल मिळू शकली नाही",
  "This acknowledgement link is not valid.": "ही पोचपावती लिंक वैध नाही.",
  "This purchase order could not be found.": "ही खरेदी ऑर्डर सापडली नाही.",
  "CRM connection is not configured": "CRM कनेक्शन अजून सेट केलेले नाही",
  "No company mailbox is configured": "कंपनीचा मेलबॉक्स अजून सेट केलेला नाही",
  "Current password is incorrect": "सध्याचा पासवर्ड चुकीचा आहे",
  "Invalid credentials": "ईमेल किंवा पासवर्ड चुकीचा आहे",
  "Not authenticated": "कृपया साइन इन करा",
  "User not found or deactivated": "खाते सापडले नाही किंवा बंद केले आहे",
  "Supplier portal endpoint — requires a supplier account": "हे फक्त पुरवठादार खात्यासाठी आहे",
  "Supplier accounts cannot switch company": "पुरवठादार खाते कंपनी बदलू शकत नाही",
  "messages cannot be empty": "संदेश रिकामा असू शकत नाही",
  "Harmony Intelligent is currently unavailable.": "Harmony Intelligent सध्या उपलब्ध नाही.",
  "The assistant could not answer right now. Please try again.":
    "सहाय्यक सध्या उत्तर देऊ शकला नाही. कृपया पुन्हा प्रयत्न करा.",
  "The file is empty.": "फाइल रिकामी आहे.",
  "File too large (max {n} MB).": "फाइल खूप मोठी आहे (कमाल {n} MB).",
  "File attachments are not configured yet (S3 bucket/keys missing).": "फाइल जोडण्याची सुविधा अजून सेट केलेली नाही.",
  "Unknown stage '{stage}'": "अज्ञात टप्पा '{stage}'",
  "Could not download the PO PDF from the CRM ({code}).": "CRM मधून PO PDF डाउनलोड करता आली नाही ({code}).",
  "Choose a valid transport mode.": "योग्य वाहतूक प्रकार निवडा.",
};
