/**
 * Marathi strings for the Supplier Assignment and Email Master screens (staff
 * pages and their employee-portal versions). Keyed by the English source text.
 */
export const MR_MANAGE: Record<string, string> = {
  // ── Navigation / access ──
  "Supplier Assignment": "सप्लायर असाइनमेंट",
  "Email Master": "ईमेल मास्टर",
  "Your account does not have access to Supplier Assignment. Ask an admin to enable it.":
    "तुमच्या खात्याला सप्लायर असाइनमेंटचा प्रवेश नाही. सुरू करण्यासाठी अ‍ॅडमिनला सांगा.",
  "Your account does not have access to Email Master. Ask an admin to enable it.":
    "तुमच्या खात्याला ईमेल मास्टरचा प्रवेश नाही. सुरू करण्यासाठी अ‍ॅडमिनला सांगा.",
  Retry: "पुन्हा प्रयत्न करा",
  Save: "सेव्ह करा",
  "Saving…": "सेव्ह होत आहे…",
  Edit: "बदला",
  Actions: "क्रिया",
  Supplier: "सप्लायर",

  // ── Supplier Assignment ──
  "Supplier Assignments": "सप्लायर असाइनमेंट",
  "Map each supplier to the people responsible for it. A supplier's incoming email is routed to those people in-app (they get a notification).":
    "प्रत्येक सप्लायरसाठी जबाबदार लोक निवडा. त्या सप्लायरचा येणारा ईमेल ॲपमध्ये त्या लोकांकडे जातो (त्यांना सूचना मिळते).",
  "Search suppliers…": "सप्लायर शोधा…",
  "Assigned people": "नेमलेले लोक",
  "No suppliers.": "सप्लायर नाहीत.",
  "Not assigned": "कोणीही नेमलेले नाही",
  "Assign people — {name}": "लोक नेमा — {name}",
  "Search people…": "लोक शोधा…",
  "No assignable users.": "नेमता येणारे वापरकर्ते नाहीत.",
  "No people match “{q}”.": "“{q}” शी जुळणारे लोक नाहीत.",
  "{n} selected": "{n} निवडले",
  "Saved assignees for {name}.": "{name} साठी नेमलेले लोक सेव्ह झाले.",
  "Could not save assignees.": "नेमलेले लोक सेव्ह करता आले नाहीत.",

  // ── Email Master ──
  "Maintain supplier recipient, CC, BCC and escalation mappings.":
    "सप्लायरचे प्राप्तकर्ता, CC, BCC आणि एस्केलेशन ईमेल सांभाळा.",
  "Search supplier / email…": "सप्लायर / ईमेल शोधा…",
  "View who changed what": "कोणी काय बदलले ते पहा",
  "Change Log": "बदल नोंद",
  "Add Mapping": "मॅपिंग जोडा",
  "Could not load email mappings.": "ईमेल मॅपिंग लोड करता आले नाहीत.",
  "Saved email mapping for {name}.": "{name} चे ईमेल मॅपिंग सेव्ह झाले.",
  "Saved, but the list could not be refreshed: {error}": "सेव्ह झाले, पण यादी रिफ्रेश झाली नाही: {error}",
  "Deleted, but the list could not be refreshed: {error}": "काढले, पण यादी रिफ्रेश झाली नाही: {error}",
  "Unable to save email mapping.": "ईमेल मॅपिंग सेव्ह करता आले नाही.",
  "Unable to delete email mapping.": "ईमेल मॅपिंग काढता आले नाही.",
  "Delete this email mapping?": "हे ईमेल मॅपिंग काढायचे?",
  "Select a supplier.": "सप्लायर निवडा.",
  "Add at least one TO email.": "किमान एक TO ईमेल जोडा.",
  "This supplier already has an active email mapping.": "या सप्लायरचे सक्रिय ईमेल मॅपिंग आधीच आहे.",
  "Supplier login provisioning": "सप्लायर लॉगिन तयार करणे",
  "No login changes — all TO emails were already provisioned.":
    "लॉगिनमध्ये बदल नाही — सर्व TO ईमेलचे लॉगिन आधीच आहेत.",
  "Logins created": "लॉगिन तयार झाले",
  "Credentials emailed to: {emails}.": "लॉगिन तपशील यांना ईमेल केले: {emails}.",
  "Email not sent (SMTP off) — share the temporary passwords securely.":
    "ईमेल पाठवला नाही (SMTP बंद) — तात्पुरते पासवर्ड सुरक्षितपणे द्या.",
  "Reactivated:": "पुन्हा सुरू केले:",
  "Re-linked to this supplier:": "या सप्लायरला पुन्हा जोडले:",
  "(the login pointed at an old or duplicate supplier record; its password is unchanged)":
    "(हे लॉगिन जुन्या किंवा डुप्लिकेट सप्लायर नोंदीला जोडलेले होते; पासवर्ड बदललेला नाही)",
  "Deactivated:": "बंद केले:",
  "Skipped (conflict):": "वगळले (संघर्ष):",
  Primary: "मुख्य",
  Escalation: "एस्केलेशन",
  Active: "सक्रिय",
  YES: "हो",
  NO: "नाही",
  "No mappings yet.": "अजून मॅपिंग नाही.",
  "No mappings match your search.": "तुमच्या शोधाशी जुळणारे मॅपिंग नाही.",
  "Supplier logins": "सप्लायर लॉगिन",
  "Delete (admin only)": "काढा (फक्त अ‍ॅडमिन)",
  "Edit Email Mapping": "ईमेल मॅपिंग बदला",
  "Add Email Mapping": "ईमेल मॅपिंग जोडा",
  "Supplier Dropdown *": "सप्लायर निवडा *",
  "Select supplier": "सप्लायर निवडा",
  inactive: "निष्क्रिय",
  "TO Emails *": "TO ईमेल *",
  "Each TO email gets a Supplier Portal login (a temporary password is emailed; they’re asked to change it on first login).":
    "प्रत्येक TO ईमेलला सप्लायर पोर्टल लॉगिन मिळते (तात्पुरता पासवर्ड ईमेल होतो; पहिल्या लॉगिनला तो बदलावा लागतो).",
  "CC Emails": "CC ईमेल",
  "BCC Emails": "BCC ईमेल",
  "Escalation Emails": "एस्केलेशन ईमेल",
  "Contact Person": "संपर्क व्यक्ती",
  Phone: "फोन",
  Remarks: "शेरा",
  "{email} is not a valid email.": "{email} हा वैध ईमेल नाही.",
};
