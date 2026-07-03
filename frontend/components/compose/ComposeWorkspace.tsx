"use client";

import { useEffect, useId, useMemo, useState } from "react";
import { Loader2, Mail, Save, Send, Sparkles, X } from "lucide-react";
import PageHeader from "@/components/layout/PageHeader";

export interface SupplierContact {
  supplier_name: string;
  to_emails: string[];
  cc_emails: string[];
}

export interface ComposeResult {
  ok: boolean;
  sent: boolean;
  status: string;
}

export interface ComposeAdapter {
  /** Whether the Supplier/Customer audience toggle is offered (staff only). */
  allowCustomer: boolean;
  compose: (body: {
    audience: "supplier" | "customer";
    to_emails: string[];
    cc_emails?: string[];
    bcc_emails?: string[];
    subject: string;
    body: string;
    supplier_name?: string | null;
    supplier_po_no?: string | null;
    send: boolean;
  }) => Promise<ComposeResult>;
  composeDraft: (body: {
    audience: "supplier" | "customer";
    instruction: string;
    subject?: string;
    supplier_name?: string | null;
    supplier_po_no?: string | null;
    recipient_name?: string | null;
  }) => Promise<{ body: string; source: "ai" | "template" }>;
  loadSupplierContacts: () => Promise<SupplierContact[]>;
}

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export default function ComposeWorkspace({
  adapter,
  title = "Compose Mail",
  description = "Write and send an email to a supplier or customer — delivered in your branded HTML format.",
}: {
  adapter: ComposeAdapter;
  title?: string;
  description?: string;
}) {
  const [audience, setAudience] = useState<"supplier" | "customer">("supplier");
  const [to, setTo] = useState<string[]>([]);
  const [cc, setCc] = useState<string[]>([]);
  const [bcc, setBcc] = useState<string[]>([]);
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const [supplierName, setSupplierName] = useState<string | null>(null);
  const [supplierPoNo, setSupplierPoNo] = useState("");
  const [instruction, setInstruction] = useState("");

  const [contacts, setContacts] = useState<SupplierContact[]>([]);
  const [sending, setSending] = useState<false | "send" | "draft">(false);
  const [drafting, setDrafting] = useState(false);
  const [toast, setToast] = useState<{ tone: "ok" | "err"; msg: string } | null>(null);

  useEffect(() => {
    adapter.loadSupplierContacts().then(setContacts).catch(() => setContacts([]));
  }, [adapter]);

  useEffect(() => {
    if (!toast) return;
    const id = setTimeout(() => setToast(null), 3000);
    return () => clearTimeout(id);
  }, [toast]);

  const emailSuggestions = useMemo(() => {
    const set = new Set<string>();
    for (const c of contacts) [...c.to_emails, ...c.cc_emails].forEach((e) => e && set.add(e));
    return [...set];
  }, [contacts]);

  const pickSupplier = (name: string) => {
    const c = contacts.find((x) => x.supplier_name === name);
    setSupplierName(name || null);
    if (c) {
      setTo(dedupe([...to, ...c.to_emails.filter(Boolean)]));
      setCc(dedupe([...cc, ...c.cc_emails.filter(Boolean)]));
    }
  };

  const canSend = to.length > 0 && subject.trim() && body.trim() && !sending;

  const runDraft = async () => {
    setDrafting(true);
    try {
      const res = await adapter.composeDraft({
        audience,
        instruction: instruction.trim(),
        subject: subject.trim() || undefined,
        supplier_name: supplierName,
        supplier_po_no: supplierPoNo.trim() || undefined,
        recipient_name: supplierName ?? undefined,
      });
      setBody(res.body);
      setToast({ tone: "ok", msg: res.source === "ai" ? "HI drafted the email." : "Draft ready (template)." });
    } catch (e) {
      setToast({ tone: "err", msg: (e as Error).message });
    } finally {
      setDrafting(false);
    }
  };

  const submit = async (send: boolean) => {
    if (to.length === 0) return setToast({ tone: "err", msg: "Add at least one recipient." });
    if (!subject.trim()) return setToast({ tone: "err", msg: "Subject is required." });
    if (!body.trim()) return setToast({ tone: "err", msg: "Message body is required." });
    setSending(send ? "send" : "draft");
    try {
      const res = await adapter.compose({
        audience,
        to_emails: to,
        cc_emails: cc,
        bcc_emails: bcc,
        subject: subject.trim(),
        body,
        supplier_name: audience === "supplier" ? supplierName : null,
        supplier_po_no: audience === "supplier" ? supplierPoNo.trim() || null : null,
        send,
      });
      if (send) {
        setToast({ tone: res.sent ? "ok" : "err", msg: res.sent ? "Email sent." : `Queued (${res.status}).` });
        if (res.sent) {
          setTo([]); setCc([]); setBcc([]); setSubject(""); setBody(""); setInstruction("");
          setSupplierName(null); setSupplierPoNo("");
        }
      } else {
        setToast({ tone: "ok", msg: "Saved as draft." });
      }
    } catch (e) {
      setToast({ tone: "err", msg: (e as Error).message });
    } finally {
      setSending(false);
    }
  };

  return (
    <div className="space-y-4">
      <PageHeader
        title={title}
        description={description}
        icon={Mail}
        tone="red"
        actions={
          toast ? (
            <span
              className={`rounded-md px-3 py-1.5 text-xs ${
                toast.tone === "ok" ? "bg-emerald-600 text-white" : "bg-signal-red text-white"
              }`}
            >
              {toast.msg}
            </span>
          ) : null
        }
      />

      <div className="mx-auto max-w-3xl space-y-4 rounded-xl border border-brand-border bg-card p-5 shadow-sm">
        {/* Audience */}
        {adapter.allowCustomer && (
          <div className="flex items-center gap-2">
            <span className="text-xs font-semibold text-brand-muted">To audience</span>
            <div className="inline-flex rounded-lg border border-brand-border bg-subtle p-0.5 text-xs font-semibold">
              {(["supplier", "customer"] as const).map((a) => (
                <button
                  key={a}
                  onClick={() => setAudience(a)}
                  className={`rounded-md px-3 py-1.5 capitalize transition ${
                    audience === a ? "bg-card text-signal-red shadow-sm" : "text-brand-muted hover:text-brand-dark"
                  }`}
                >
                  {a}
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Supplier picker + PO (supplier audience) */}
        {audience === "supplier" && (
          <div className="grid gap-3 sm:grid-cols-2">
            <label className="block">
              <span className="mb-1 block text-[11px] font-semibold uppercase tracking-wider text-brand-muted">
                Load recipients from supplier
              </span>
              <select
                value={supplierName ?? ""}
                onChange={(e) => pickSupplier(e.target.value)}
                className="input h-9 w-full text-sm"
              >
                <option value="">Select a supplier…</option>
                {contacts.map((c) => (
                  <option key={c.supplier_name} value={c.supplier_name}>
                    {c.supplier_name}
                  </option>
                ))}
              </select>
            </label>
            <label className="block">
              <span className="mb-1 block text-[11px] font-semibold uppercase tracking-wider text-brand-muted">
                Link PO No. (optional)
              </span>
              <input
                value={supplierPoNo}
                onChange={(e) => setSupplierPoNo(e.target.value)}
                placeholder="e.g. 000449"
                className="input h-9 w-full text-sm"
              />
            </label>
          </div>
        )}

        <ChipField label="To" values={to} onChange={setTo} suggestions={emailSuggestions} required />
        <ChipField label="Cc" values={cc} onChange={setCc} suggestions={emailSuggestions} />
        <ChipField label="Bcc" values={bcc} onChange={setBcc} suggestions={emailSuggestions} />

        <label className="block">
          <span className="mb-1 block text-[11px] font-semibold uppercase tracking-wider text-brand-muted">Subject</span>
          <input
            value={subject}
            onChange={(e) => setSubject(e.target.value)}
            placeholder="Subject line"
            className="input h-9 w-full text-sm"
          />
        </label>

        {/* HI assist */}
        <div className="rounded-lg border border-signal-red/20 bg-red-50/50 p-3">
          <div className="mb-2 flex items-center gap-1.5 text-xs font-semibold text-signal-red">
            <Sparkles size={14} /> Harmony Intelligence — draft for you
          </div>
          <div className="flex flex-col gap-2 sm:flex-row">
            <input
              value={instruction}
              onChange={(e) => setInstruction(e.target.value)}
              placeholder="What should this email say? e.g. request an updated commitment date for PO 000449"
              className="input h-9 flex-1 text-sm"
            />
            <button onClick={runDraft} disabled={drafting} className="btn-outline h-9 shrink-0">
              {drafting ? <Loader2 size={14} className="animate-spin" /> : <Sparkles size={14} />}
              Draft with HI
            </button>
          </div>
        </div>

        <label className="block">
          <span className="mb-1 block text-[11px] font-semibold uppercase tracking-wider text-brand-muted">Message</span>
          <textarea
            value={body}
            onChange={(e) => setBody(e.target.value)}
            rows={10}
            placeholder="Write your message… (sent in your branded HTML format)"
            className="w-full resize-y rounded-lg border border-brand-border bg-subtle px-3 py-2.5 text-sm outline-none focus:border-signal-red/40 focus:bg-card"
          />
        </label>

        <div className="flex items-center justify-between gap-2">
          <span className="text-[11px] text-brand-muted">Delivered as branded HTML via the mail engine.</span>
          <div className="flex items-center gap-2">
            <button onClick={() => submit(false)} disabled={!!sending} className="btn-ghost h-9">
              {sending === "draft" ? <Loader2 size={14} className="animate-spin" /> : <Save size={14} />} Save draft
            </button>
            <button
              onClick={() => submit(true)}
              disabled={!canSend}
              className="inline-flex h-9 items-center gap-1.5 rounded-md bg-signal-red px-4 text-sm font-medium text-white hover:opacity-90 disabled:opacity-50"
            >
              {sending === "send" ? <Loader2 size={14} className="animate-spin" /> : <Send size={14} />} Send
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

function dedupe(list: string[]): string[] {
  return [...new Set(list.filter(Boolean))];
}

function ChipField({
  label,
  values,
  onChange,
  suggestions,
  required,
}: {
  label: string;
  values: string[];
  onChange: (v: string[]) => void;
  suggestions: string[];
  required?: boolean;
}) {
  const [input, setInput] = useState("");
  const listId = useId();

  const add = (raw: string) => {
    const v = raw.trim().replace(/[;,]+$/, "");
    if (!v) return;
    if (!EMAIL_RE.test(v)) return; // ignore obviously invalid tokens
    onChange(dedupe([...values, v]));
    setInput("");
  };

  return (
    <label className="block">
      <span className="mb-1 block text-[11px] font-semibold uppercase tracking-wider text-brand-muted">
        {label} {required && <span className="text-signal-red">*</span>}
      </span>
      <div className="flex flex-wrap items-center gap-1.5 rounded-lg border border-brand-border bg-subtle px-2 py-1.5 focus-within:border-signal-red/40 focus-within:bg-card">
        {values.map((e) => (
          <span key={e} className="inline-flex items-center gap-1 rounded bg-card px-2 py-0.5 text-xs text-brand-dark ring-1 ring-brand-border">
            {e}
            <button type="button" onClick={() => onChange(values.filter((x) => x !== e))} className="text-brand-muted hover:text-signal-red">
              <X size={11} />
            </button>
          </span>
        ))}
        <input
          value={input}
          list={listId}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === "," || e.key === ";") {
              e.preventDefault();
              add(input);
            } else if (e.key === "Backspace" && !input && values.length) {
              onChange(values.slice(0, -1));
            }
          }}
          onBlur={() => add(input)}
          placeholder={values.length ? "" : "type an email, Enter to add"}
          className="min-w-[12rem] flex-1 bg-transparent px-1 py-0.5 text-sm outline-none"
        />
        <datalist id={listId}>
          {suggestions.map((s) => (
            <option key={s} value={s} />
          ))}
        </datalist>
      </div>
    </label>
  );
}
