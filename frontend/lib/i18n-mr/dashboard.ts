// Marathi strings for the shared dashboard screens (merged into MR in ../i18n-mr.ts).
export const MR_DASHBOARD: Record<string, string> = {
  // ── KPI strip / overview charts ──
  "Procurement overview": "खरेदीचा आढावा",
  "Total records": "एकूण नोंदी",
  "Red signal": "लाल सिग्नल",
  "HI required": "HI आवश्यक",
  "HI Req.": "HI आवश्यक",
  "Workload Overview": "कामाचा आढावा",
  "Signal Distribution": "सिग्नल वाटप",
  Green: "हिरवा",
  Yellow: "पिवळा",
  Red: "लाल",
  Black: "काळा",

  // ── Harmony Intelligent insights ──
  "{n} BLACK record(s) flagged for escalation.": "{n} काळ्या नोंदी एस्केलेशनसाठी चिन्हांकित.",
  "{n} RED record(s) overdue — urgent follow-up due today.":
    "{n} लाल नोंदींची मुदत संपली — आज तातडीने फॉलो-अप करा.",
  "{n} record(s) need AI-generated follow-up mails.": "{n} नोंदींसाठी AI फॉलो-अप मेल बनवणे आवश्यक.",
  "{n} shipment(s) are due today — confirm dispatch.": "{n} शिपमेंटची आज मुदत — डिस्पॅच निश्चित करा.",
  "{supplier} has {n} BLACK / RED PO line(s).": "{supplier} कडे {n} काळ्या / लाल PO ओळी आहेत.",
  "All records are on track. No immediate action required.":
    "सर्व नोंदी वेळेवर आहेत. सध्या कोणतीही कृती आवश्यक नाही.",

  // ── Tasks summary card ──
  "Open →": "उघडा →",
  "To do": "करायचे",
  Waiting: "प्रतीक्षेत",
  "In progress": "काम सुरू",
  Critical: "गंभीर",

  // ── PO expandable table ──
  "No purchase orders to show.": "दाखवण्यासाठी कोणत्याही खरेदी ऑर्डर नाहीत.",
  "Show / hide material columns": "मालाचे कॉलम दाखवा / लपवा",
  "Material columns": "मालाचे कॉलम",
  Materials: "माल",
  "Earliest Ship": "सर्वात लवकर शिपिंग",
  UoM: "एकक",
  Pending: "बाकी",
  "PO Status": "PO स्थिती",
  Received: "मिळाले",
  "Partly recd": "अंशतः मिळाले",
  Awaiting: "प्रतीक्षेत",
  "{n} more ref": "आणखी {n} संदर्भ",
  "{n} more refs": "आणखी {n} संदर्भ",
  ESCALATED: "एस्केलेट केलेले",
  "Direct PO": "थेट PO",
  "for {name}": "{name} साठी",
  "Internal only — the supplier will not see this PO until it is approved in the CRM":
    "फक्त अंतर्गत — CRM मध्ये मंजूर होईपर्यंत पुरवठादाराला हा PO दिसणार नाही",
  "Request cancel": "रद्द करण्याची विनंती",
  "Loading details…": "तपशील लोड होत आहेत…",
  "No materials.": "माल नाही.",
  "Communication ({n})": "संवाद ({n})",
  "No messages on this PO yet.": "या PO वर अजून कोणतेही संदेश नाहीत.",
  "Could not load details.": "तपशील लोड करता आले नाहीत.",
  In: "आलेले",
  Out: "गेलेले",
  "(no subject)": "(विषय नाही)",
  "from {email}": "{email} कडून",
  "to {email}": "{email} ला",
  "Request PO cancellation": "PO रद्द करण्याची विनंती",
  "Raise a cancellation for PO": "या PO साठी रद्द करण्याची विनंती पाठवायची:",
  "The PO will be marked": "निश्चित होईपर्यंत हा PO",
  "until it is confirmed.": "म्हणून दिसेल.",
  "Remark (reason for cancellation — sent to the ERP)": "टिप्पणी (रद्द करण्याचे कारण — ERP ला पाठवले जाईल)",

  // ── PO PDF ──
  "Download PO PDF": "PO PDF डाउनलोड करा",
  "PO PDF download failed.": "PO PDF डाउनलोड अयशस्वी.",

  // ── Workload report widgets ──
  "Export Excel": "Excel एक्सपोर्ट",
  "Retry export": "पुन्हा एक्सपोर्ट करा",
  "Download as .xlsx for meetings": "मीटिंगसाठी .xlsx म्हणून डाउनलोड करा",
  "Task throughput — last 14 days": "टास्कचा वेग — मागील 14 दिवस",
  "No tasks yet.": "अजून टास्क नाहीत.",
  "Pending PO lines ({n})": "बाकी PO ओळी ({n})",
  "Not yet dispatched/closed — earliest ship date first.":
    "अजून डिस्पॅच/बंद न झालेल्या — सर्वात लवकरची शिपिंग तारीख आधी.",
  "PO No.": "PO क्र.",
  "Customer PO": "ग्राहक PO",
  "PO date": "PO तारीख",
  "Ship date": "शिपिंग तारीख",
  "Days overdue": "मुदत संपून दिवस",
  "Follow-ups": "फॉलो-अप",
  "Nothing pending.": "काहीही बाकी नाही.",
  "Open tasks ({n})": "चालू टास्क ({n})",
  "Everything not done — earliest due first.": "पूर्ण न झालेले सर्व — सर्वात आधीची मुदत आधी.",
  "No open tasks.": "चालू टास्क नाहीत.",
  Task: "टास्क",
  "PO {po}": "PO {po}",
};
