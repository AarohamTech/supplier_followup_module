// Marathi strings for the Supplier Portal (merged into MR in ../i18n-mr.ts).
// Text that already has Marathi elsewhere (Dashboard, Tasks, Loading…, Cancel,
// Status, the ASN table/drawer…) is reused from the other files, not repeated.
// Business identifiers (PO, ASN, CRM, ETA) and product names (Outlook) stay in
// Latin script, as in the rest of the dictionary.
export const MR_PORTAL: Record<string, string> = {
  // ── Topbar (components/portal/SupplierShell) ──
  "Supplier Portal": "पुरवठादार पोर्टल",
  "Purchase orders, communication and shipments": "खरेदी ऑर्डर, संवाद आणि शिपमेंट",

  // ── Sidebar menu (components/portal/SupplierSidebar) ──
  "Supplier navigation": "पुरवठादार मेनू",
  "Orders and shipments": "ऑर्डर आणि शिपमेंट",
  "Raise an Issue": "समस्या नोंदवा",
  "ASN Portal": "ASN पोर्टल",

  // ── Counts (singular / plural picked before t()) ──
  "{n} material": "{n} माल",
  "{n} materials": "{n} माल",
  "{n} ASN": "{n} ASN",
  "{n} ASNs": "{n} ASN",

  // ── Supplier-facing PO status chips (lib/messageLabels) ──
  "Action needed": "कृती आवश्यक",
  "On track": "वेळेवर",
  "Escalated to buyer": "खरेदीदाराकडे एस्केलेट केले",
  "Escalated to buyer team": "खरेदी टीमकडे एस्केलेट केले",

  // ── Dashboard (app/portal/page.tsx) ──
  "Your purchase orders and shipment notices at a glance.": "तुमच्या खरेदी ऑर्डर आणि शिपमेंट सूचना एका नजरेत.",
  "Go to ASN Portal": "ASN पोर्टलवर जा",
  "Total POs": "एकूण PO",
  "Completed POs": "पूर्ण PO",
  "Awaiting delivery": "डिलिव्हरीची प्रतीक्षा",
  "Delivered via ASN": "ASN द्वारे डिलिव्हर झाले",
  "Blocked / Black": "अडकलेले / काळे",
  "Critical attention": "तातडीने लक्ष द्या",
  "Shipments (ASN)": "शिपमेंट (ASN)",
  "PO Signal Mix": "PO सिग्नल वाटप",
  "Review PO-wise material status and progress.": "PO नुसार मालाची स्थिती आणि प्रगती पाहा.",
  "Create and track Advance Shipping Notices.": "आगाऊ शिपिंग सूचना (ASN) तयार करा आणि ट्रॅक करा.",

  // ── Critical (Black) POs (components/portal/CriticalPos) ──
  "No critical (Black) POs": "कोणतेही गंभीर (काळे) PO नाहीत",
  "You have no orders flagged Black right now.": "सध्या तुमची कोणतीही ऑर्डर काळ्या सिग्नलवर नाही.",
  "Critical — Black POs": "गंभीर — काळे PO",
  "Action required": "कृती आवश्यक",
  "Overdue {d}d {h}h {m}m {s}s": "मुदत संपली {d}दि {h}तास {m}मि {s}से",
  "Due in {d}d {h}h {m}m": "{d}दि {h}तास {m}मि मध्ये मुदत",

  // ── My Purchase Orders (app/portal/pos/page.tsx) ──
  "All your POs. Escalated orders are pinned to the top — click a row for details.":
    "तुमचे सर्व PO. एस्केलेट केलेल्या ऑर्डर सर्वात वर दिसतात — तपशीलासाठी ओळीवर क्लिक करा.",
  "Search PO / CRM…": "PO / CRM शोधा…",
  "Earliest Due": "सर्वात जवळची मुदत",
  ASNs: "ASN",
  Messages: "संदेश",
  "No purchase orders found.": "कोणत्याही खरेदी ऑर्डर सापडल्या नाहीत.",

  // ── PO detail (app/portal/pos/[supplier_po_no]/page.tsx) ──
  "Back to purchase orders": "खरेदी ऑर्डरकडे परत",
  "Review material commitments, buyer tasks and shipment progress for this purchase order.":
    "या खरेदी ऑर्डरसाठी मालाची वचने, खरेदीदाराचे टास्क आणि शिपमेंटची प्रगती पाहा.",
  "Open communication": "संवाद उघडा",
  "Escalate this purchase order": "ही खरेदी ऑर्डर एस्केलेट करा",
  "This alerts the buyer team immediately and opens a priority task on their side. Add a short reason so they can act fast.":
    "यामुळे खरेदी टीमला लगेच सूचना जाते आणि त्यांच्याकडे प्राधान्याचा टास्क उघडतो. त्यांना लवकर कृती करता यावी म्हणून थोडक्यात कारण लिहा.",
  "e.g. Production line blocked — need dispatch confirmation today":
    "उदा. उत्पादन लाइन थांबली आहे — आजच डिस्पॅचची पुष्टी हवी",
  "Confirm escalation": "एस्केलेशनची पुष्टी करा",
  "Escalation sent — your buyer team has been notified and will prioritise this PO.":
    "एस्केलेशन पाठवले — तुमच्या खरेदी टीमला कळवले आहे आणि ते या PO ला प्राधान्य देतील.",
  "CRM reference": "CRM संदर्भ",
  Commitments: "वचने",
  Shipments: "शिपमेंट",
  "{n} of {total}": "{total} पैकी {n}",
  "Material commitments": "मालाची वचने",
  "Confirm dispatch dates and current material status.": "डिस्पॅच तारखा आणि मालाची सध्याची स्थिती निश्चित करा.",
  "{n}/{total} recorded": "{n}/{total} नोंदवले",
  CRM: "CRM",
  "Required by": "आवश्यक तारीख",
  "No materials found for this order.": "या ऑर्डरसाठी कोणताही माल सापडला नाही.",
  "Optional note": "टिप्पणी (ऐच्छिक)",
  "Add a dispatch date to stop automated follow-ups for that material and notify your buyer.":
    "त्या मालाचे स्वयंचलित फॉलो-अप थांबवण्यासाठी आणि खरेदीदाराला कळवण्यासाठी डिस्पॅच तारीख टाका.",
  "Save commitments": "वचने सेव्ह करा",
  "Commitment dates saved — your buyer has been notified.": "वचन तारखा सेव्ह झाल्या — तुमच्या खरेदीदाराला कळवले आहे.",
  "Buyer tasks": "खरेदीदाराचे टास्क",
  "Read-only actions tracked by the buyer's team.": "खरेदी टीम ट्रॅक करत असलेली कामे (फक्त पाहण्यासाठी).",
  "No buyer tasks for this purchase order.": "या खरेदी ऑर्डरसाठी खरेदीदाराचे कोणतेही टास्क नाहीत.",
  "Advance Shipping Notices linked to this order.": "या ऑर्डरशी जोडलेल्या आगाऊ शिपिंग सूचना (ASN).",
  // Commitment status choices — shown translated, saved as the English code.
  CONFIRMED: "निश्चित",
  DELAYED: "विलंब",
  PARTIAL: "अंशतः",
  DISPATCHED: "पाठवले",
  "ON HOLD": "थांबवले",
  CANCELLED: "रद्द",
  // Buyer task statuses (raw codes and their humanized form).
  TODO: "करायचे",
  BACKLOG: "बॅकलॉग",
  "IN PROGRESS": "काम सुरू",
  "WAITING SUPPLIER": "पुरवठादाराची प्रतीक्षा",
  "WAITING CUSTOMER": "ग्राहकाची प्रतीक्षा",
  BLOCKED: "अडकलेले",
  DONE: "पूर्ण",
  Todo: "करायचे",
  "Waiting supplier": "पुरवठादाराची प्रतीक्षा",
  "Waiting customer": "ग्राहकाची प्रतीक्षा",

  // ── Acknowledge PO (components/portal/PoAckButton) ──
  "Acknowledge PO": "PO ची पोचपावती द्या",
  "Acknowledged in the portal": "पोर्टलमध्ये पोचपावती दिली",
  "Acknowledged on {date}": "{date} रोजी पोचपावती दिली",
  "Confirm that you have received this purchase order": "ही खरेदी ऑर्डर मिळाल्याची पुष्टी करा",

  // ── Shipment Tracking (app/portal/asn/page.tsx) ──
  "Shipment Tracking": "शिपमेंट ट्रॅकिंग",
  "Create Advance Shipping Notices and track them to delivery.":
    "आगाऊ शिपिंग सूचना (ASN) तयार करा आणि डिलिव्हरीपर्यंत ट्रॅक करा.",
  "Create New ASN": "नवीन ASN तयार करा",
  "Active Shipments": "चालू शिपमेंट",

  // ── Create ASN form (components/portal/AsnCreateModal) ──
  "Select a PO reference.": "PO संदर्भ निवडा.",
  "Add at least one shipped line to submit.": "सबमिट करण्यासाठी किमान एक पाठवलेली ओळ जोडा.",
  "PO Reference *": "PO संदर्भ *",
  "Select a purchase order": "खरेदी ऑर्डर निवडा",
  "Courier (for live tracking)": "कुरिअर (थेट ट्रॅकिंगसाठी)",
  "Tracking No": "ट्रॅकिंग क्र.",
  "Dispatch Date": "डिस्पॅच तारीख",
  Origin: "पाठवण्याचे ठिकाण",
  Destination: "पोहोचण्याचे ठिकाण",
  "Estimated Delivery (ETA)": "अपेक्षित डिलिव्हरी (ETA)",
  "e.g. Maersk Line": "उदा. Maersk Line",
  "e.g. MSK-L81122": "उदा. MSK-L81122",
  "— None —": "— काहीही नाही —",
  SEA: "समुद्र",
  AIR: "हवाई",
  ROAD: "रस्ता",
  RAIL: "रेल्वे",
  "Shipped Materials": "पाठवलेला माल",
  "Select a PO to load its materials.": "माल पाहण्यासाठी PO निवडा.",
  "Loading materials…": "माल लोड होत आहे…",
  "No materials found for this PO.": "या PO साठी कोणताही माल सापडला नाही.",
  Ship: "पाठवा",
  "PO Qty": "PO नग",
  "Qty Shipped": "पाठवलेले नग",
  "Invoice No": "इनव्हॉइस क्र.",
  "Save Draft": "मसुदा सेव्ह करा",
  "Submitting…": "सबमिट होत आहे…",

  // ── Shipment map (components/portal/ShipmentMap*) ──
  "Loading map…": "नकाशा लोड होत आहे…",
  "No mappable checkpoints yet.": "नकाशावर दाखवण्यासाठी अजून कोणतेही टप्पे नाहीत.",
  "Current location": "सध्याचे ठिकाण",

  // ── Communication Hub (components/portal/PortalCommHub) ──
  "Message your buyer about any PO. Replies appear here live.":
    "कोणत्याही PO बद्दल तुमच्या खरेदीदाराला संदेश पाठवा. उत्तरे इथे लगेच दिसतात.",
  "Message suppliers on the purchase orders assigned to you.":
    "तुमच्याकडे सोपवलेल्या खरेदी ऑर्डरवर पुरवठादारांना संदेश पाठवा.",
  "Search PO or counterparty…": "PO किंवा संपर्क व्यक्ती शोधा…",
  Buyer: "खरेदीदार",
  "Your buyer": "तुमचा खरेदीदार",
  "Loading messages…": "संदेश लोड होत आहेत…",
  "No messages yet. Start the conversation below.": "अजून संदेश नाहीत. खाली संभाषण सुरू करा.",
  "Type your message…  (Enter to send, Shift+Enter for a new line; drop files to attach)":
    "तुमचा संदेश लिहा…  (पाठवण्यासाठी Enter, नवीन ओळीसाठी Shift+Enter; फाइल जोडण्यासाठी इथे टाका)",
  "Write this message in Outlook (or your mail app) instead":
    "हा संदेश त्याऐवजी Outlook मध्ये (किंवा तुमच्या मेल ॲपमध्ये) लिहा",
  "Preparing Outlook…": "Outlook तयार होत आहे…",
  "Outlook is not available for this PO right now — send your message here instead":
    "सध्या या PO साठी Outlook उपलब्ध नाही — त्याऐवजी तुमचा संदेश इथे पाठवा",
  "Attach your files again in Outlook — they can't be passed over to it.":
    "Outlook मध्ये फाइल पुन्हा जोडा — त्या तिकडे पाठवता येत नाहीत.",
  "Send message": "संदेश पाठवा",
  "Select a purchase order to view the conversation.": "संभाषण पाहण्यासाठी खरेदी ऑर्डर निवडा.",
  Context: "माहिती",
  "Select a PO to see its details.": "तपशील पाहण्यासाठी PO निवडा.",
  "Committed: {date}": "वचन दिलेली तारीख: {date}",
  "Tasks ({n})": "टास्क ({n})",
  "No tasks for this PO.": "या PO साठी कोणतेही टास्क नाहीत.",
  "Unread replies": "न वाचलेली उत्तरे",

  // ── Raise an Issue (app/portal/issues/page.tsx) ──
  "Tell your buyer team about a problem — quality, documents, payment, anything. They are notified immediately.":
    "तुमच्या खरेदी टीमला कोणत्याही समस्येबद्दल सांगा — गुणवत्ता, कागदपत्रे, पेमेंट, काहीही. त्यांना लगेच कळवले जाते.",
  "Issue submitted — the buyer team has been notified (ticket #{id}).":
    "समस्या नोंदवली — खरेदी टीमला कळवले आहे (तिकीट #{id}).",
  "Subject *": "विषय *",
  "e.g. Drawing revision missing for PO 2627-002342": "उदा. PO 2627-002342 साठी ड्रॉइंग रिव्हिजन मिळाले नाही",
  "Related PO (optional)": "संबंधित PO (ऐच्छिक)",
  "— No specific PO —": "— कोणताही विशिष्ट PO नाही —",
  "Describe the issue — what happened, what you need from the buyer team, any deadlines…":
    "समस्येचे वर्णन करा — काय झाले, खरेदी टीमकडून काय हवे, कोणती मुदत…",
  "Submit issue": "समस्या सबमिट करा",

  // ── HI Assistant (app/portal/assistant/page.tsx) ──
  "Ask about {name} purchase orders and shipments — it reads your live data.":
    "{name} च्या खरेदी ऑर्डर आणि शिपमेंटबद्दल विचारा — ते तुमची थेट माहिती वाचते.",
  "Ask about your purchase orders and shipments — it reads your live data.":
    "तुमच्या खरेदी ऑर्डर आणि शिपमेंटबद्दल विचारा — ते तुमची थेट माहिती वाचते.",
  "Assistant is currently unavailable": "सहाय्यक सध्या उपलब्ध नाही",
  "Start a conversation. Try:": "संभाषण सुरू करा. हे विचारून पाहा:",
  "Which of my POs are most at risk right now?": "सध्या माझे कोणते PO सर्वात जास्त धोक्यात आहेत?",
  "What's the status of my latest purchase order?": "माझ्या नवीनतम खरेदी ऑर्डरची स्थिती काय आहे?",
  "Show the message history for my most delayed PO.": "माझ्या सर्वात उशीर झालेल्या PO चा संदेश इतिहास दाखवा.",
  "Reading your question…": "तुमचा प्रश्न वाचत आहे…",
  "Searching your POs & shipments…": "तुमचे PO आणि शिपमेंट शोधत आहे…",
  "Reviewing your order history & messages…": "तुमचा ऑर्डर इतिहास आणि संदेश तपासत आहे…",
  "Composing the answer…": "उत्तर तयार करत आहे…",
  "Ask about your orders…  (Enter to send, Shift+Enter for a new line)":
    "तुमच्या ऑर्डरबद्दल विचारा…  (पाठवण्यासाठी Enter, नवीन ओळीसाठी Shift+Enter)",

  // ── First sign-in password change (components/portal/PortalChangePassword) ──
  "Set a new password": "नवीन पासवर्ड सेट करा",
  "Welcome, {name}. For your security, choose a new password before continuing.":
    "स्वागत आहे, {name}. तुमच्या सुरक्षिततेसाठी पुढे जाण्यापूर्वी नवीन पासवर्ड निवडा.",
  "Welcome. For your security, choose a new password before continuing.":
    "स्वागत आहे. तुमच्या सुरक्षिततेसाठी पुढे जाण्यापूर्वी नवीन पासवर्ड निवडा.",
  "Temporary password": "तात्पुरता पासवर्ड",
  "The password we emailed you": "आम्ही ईमेलने पाठवलेला पासवर्ड",
  "New password": "नवीन पासवर्ड",
  "At least 8 characters": "किमान 8 अक्षरे",
  "Confirm new password": "नवीन पासवर्डची पुष्टी करा",
  "Re-enter new password": "नवीन पासवर्ड पुन्हा टाका",
  "New password must be at least 8 characters.": "नवीन पासवर्ड किमान 8 अक्षरांचा असावा.",
  "New password and confirmation do not match.": "नवीन पासवर्ड आणि पुष्टी जुळत नाहीत.",
  "Could not change password.": "पासवर्ड बदलता आला नाही.",
  "Saving...": "सेव्ह होत आहे...",
  "Set password & continue": "पासवर्ड सेट करा आणि पुढे जा",

  // ── Public PO acknowledgement page (app/po-ack/[token], opened from the mail) ──
  "Purchase order acknowledgement": "खरेदी ऑर्डरची पोचपावती",
  "Link not valid": "लिंक वैध नाही",
  "This link could not be processed.": "ही लिंक उघडता आली नाही.",
  "Please reply to the follow-up email or contact your buyer to acknowledge this PO.":
    "या PO ची पोचपावती देण्यासाठी फॉलो-अप ईमेलला उत्तर द्या किंवा तुमच्या खरेदीदाराशी संपर्क साधा.",
  "Acknowledge PO {ref}": "PO {ref} ची पोचपावती द्या",
  "For {supplier}.": "{supplier} साठी.",
  "Press the button to confirm you received this purchase order. Your buyer will be notified.":
    "ही खरेदी ऑर्डर मिळाल्याची पुष्टी करण्यासाठी बटण दाबा. तुमच्या खरेदीदाराला कळवले जाईल.",
  "Thank you — PO acknowledged": "धन्यवाद — PO ची पोचपावती दिली",
  "PO already acknowledged": "PO ची पोचपावती आधीच दिली आहे",
  "{po} was acknowledged by {supplier} on {when}. Your buyer has been notified.":
    "{supplier} यांनी {when} रोजी {po} ची पोचपावती दिली. तुमच्या खरेदीदाराला कळवले आहे.",
  "{po} was acknowledged on {when}. Your buyer has been notified.":
    "{when} रोजी {po} ची पोचपावती दिली. तुमच्या खरेदीदाराला कळवले आहे.",
  "{po} was already acknowledged on {when}. Nothing more is needed.":
    "{po} ची पोचपावती {when} रोजी आधीच दिली आहे. आणखी काही करण्याची गरज नाही.",
  "Acknowledging confirms you received the order. Please still enter committed dispatch dates in the supplier portal.":
    "पोचपावती दिल्याने ऑर्डर मिळाल्याची पुष्टी होते. तरीही कृपया पुरवठादार पोर्टलमध्ये डिस्पॅचच्या वचन दिलेल्या तारखा भरा.",
};
