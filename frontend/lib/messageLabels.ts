/**
 * Human labels for the raw enums that message bubbles and PO headers used to
 * show verbatim (MAILTO_OPENED, HUB_REPLY_OUTLOOK, BLACK, …). One map, used by
 * the staff Communication Hub and the supplier portal alike.
 *
 * Labels are English source strings: staff screens pass them through t(), so
 * the Marathi dictionary can translate them.
 */

export interface ChipLabel {
  label: string;
  /** Tailwind classes for the chip background + text colour. */
  cls: string;
}

const GREEN = "bg-emerald-50 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300";
const BLUE = "bg-blue-50 text-blue-700 dark:bg-blue-500/15 dark:text-blue-300";
const SKY = "bg-sky-50 text-sky-700 dark:bg-sky-500/15 dark:text-sky-300";
const AMBER = "bg-amber-50 text-amber-700 dark:bg-amber-500/15 dark:text-amber-300";
const RED = "bg-red-50 text-signal-red dark:bg-red-500/15";
const VIOLET = "bg-violet-50 text-violet-700 dark:bg-violet-500/15 dark:text-violet-300";
const GREY = "bg-subtle text-brand-muted";

/** Delivery status of a message (MailHistory.sent_status / CommunicationMessage.status). */
const MESSAGE_STATUS: Record<string, ChipLabel> = {
  SENT: { label: "Sent", cls: GREEN },
  SENT_MANUALLY: { label: "Sent manually", cls: GREEN },
  RECEIVED: { label: "Received", cls: BLUE },
  READY: { label: "Queued", cls: AMBER },
  QUEUED: { label: "Queued", cls: AMBER },
  PENDING: { label: "Pending", cls: AMBER },
  HELD: { label: "Held", cls: AMBER },
  SENDING: { label: "Sending", cls: AMBER },
  DRAFT: { label: "Draft", cls: GREY },
  COPIED: { label: "Copied", cls: GREY },
  MAILTO_OPENED: { label: "Opened in Outlook", cls: SKY },
  FAILED: { label: "Failed", cls: RED },
  ERROR: { label: "Failed", cls: RED },
  BOUNCED: { label: "Bounced", cls: RED },
  NO_EMAIL: { label: "No email on file", cls: RED },
  CANCELLED: { label: "Cancelled", cls: GREY },
  SKIPPED: { label: "Skipped", cls: GREY },
  APPROVED: { label: "Approved", cls: GREEN },
};

/** Channel / kind of a message (mail_type, or the row source). */
const MESSAGE_KIND: Record<string, ChipLabel> = {
  HUB_REPLY_OUTLOOK: { label: "Outlook reply", cls: SKY },
  HUB_REPLY: { label: "Hub reply", cls: GREY },
  HUB_COMPOSE: { label: "New mail", cls: GREY },
  HUB_PORTAL_MESSAGE: { label: "Portal", cls: VIOLET },
  PORTAL_MESSAGE: { label: "Portal", cls: VIOLET },
  EMPLOYEE_MESSAGE: { label: "Portal", cls: VIOLET },
  PORTAL_ESCALATION: { label: "Escalation", cls: RED },
  PO_FOLLOWUP_GREEN: { label: "Follow-up · On track", cls: GREEN },
  PO_FOLLOWUP_YELLOW: { label: "Follow-up · Reminder", cls: AMBER },
  PO_FOLLOWUP_RED: { label: "Follow-up · Action needed", cls: RED },
  PO_FOLLOWUP_BLACK: { label: "Follow-up · Overdue", cls: RED },
  PO_FOLLOWUP_GROUP: { label: "Follow-up", cls: GREY },
  GREEN_PO_RELEASE: { label: "PO release", cls: GREEN },
  YELLOW_REMINDER: { label: "Reminder", cls: AMBER },
  BLACK_ESCALATION: { label: "Escalation", cls: RED },
  GENERAL_FOLLOWUP: { label: "Follow-up", cls: GREY },
  AUTO_ACK: { label: "Auto acknowledgement", cls: GREY },
  HI_AGENT_SEND: { label: "HI agent", cls: VIOLET },
  HI_AGENT_REPLY: { label: "HI agent", cls: VIOLET },
  HI_FOLLOWUP_FORWARD: { label: "HI agent", cls: VIOLET },
  HI_SCHEDULED_SUMMARY: { label: "HI summary", cls: VIOLET },
  CUSTOMER_REPLY: { label: "Customer reply", cls: GREY },
  MAIL: { label: "Email", cls: GREY },
  MAIL_HISTORY: { label: "Email", cls: GREY },
  COMMUNICATION_MESSAGES: { label: "Email", cls: GREY },
};

/** "SOME_RAW_ENUM" → "Some raw enum" — fallback for values not in a map. */
export function humanizeEnum(value?: string | null): string {
  const s = (value || "").trim();
  if (!s) return "";
  const words = s.replace(/[_\-]+/g, " ").toLowerCase();
  return words.charAt(0).toUpperCase() + words.slice(1);
}

function lookup(map: Record<string, ChipLabel>, value?: string | null): ChipLabel {
  const key = (value || "").trim().toUpperCase();
  return map[key] ?? { label: humanizeEnum(value), cls: GREY };
}

/** Delivery status chip (Sent / Received / Queued / Opened in Outlook / …). */
export function messageStatusChip(status?: string | null): ChipLabel {
  return lookup(MESSAGE_STATUS, status);
}

/** Channel chip for a mail_type / source value (Portal / Outlook reply / …). */
export function messageKindChip(kind?: string | null): ChipLabel {
  const key = (kind || "").trim().toUpperCase();
  if (MESSAGE_KIND[key]) return MESSAGE_KIND[key];
  if (MESSAGE_STATUS[key]) return MESSAGE_STATUS[key];
  if (key.startsWith("PO_FOLLOWUP")) return { label: "Follow-up", cls: GREY };
  return { label: humanizeEnum(kind), cls: GREY };
}

/**
 * Supplier-facing PO status. The raw follow-up signal (BLACK/RED/…) and the
 * internal "Escalated" flag are buyer-side terms; suppliers see these instead.
 */
const SUPPLIER_SIGNAL: Record<string, ChipLabel> = {
  BLACK: { label: "Overdue", cls: "bg-ink text-white" },
  RED: { label: "Action needed", cls: RED },
  YELLOW: { label: "Reminder", cls: AMBER },
  GREEN: { label: "On track", cls: GREEN },
};

export function supplierSignalChip(signal?: string | null): ChipLabel | null {
  const key = (signal || "").trim().toUpperCase();
  return SUPPLIER_SIGNAL[key] ?? null;
}

export const SUPPLIER_ESCALATED_LABEL = "Escalated to buyer";
