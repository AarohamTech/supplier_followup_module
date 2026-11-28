"use client";

// Public PO acknowledgement page — opened from the "Acknowledge PO" button in a
// follow-up mail. No login: the signed token in the URL names the company,
// supplier and PO. Opening the page only reads the status; the supplier must
// press "Acknowledge PO" to record it (mail link scanners open links too, and
// must not create false acknowledgements). Opening it again shows when.
// English / Marathi switch in the card header (same saved choice as the portal).

import { Fragment, useEffect, useRef, useState, type ReactNode } from "react";
import { useParams } from "next/navigation";
import { AlertTriangle, CheckCircle2, Loader2 } from "lucide-react";

import { LogoLockup } from "@/components/brand/Logo";
import { publicPoAck } from "@/lib/api";
import { fmtAckTime } from "@/lib/format";
import { LanguageToggle, useErrorText, useT } from "@/lib/i18n";
import type { PoAckStatus } from "@/lib/types";

/** Fill `{name}` placeholders in an already-translated sentence with elements,
 *  so bold parts stay bold whatever the word order of the language. */
function rich(text: string, parts: Record<string, ReactNode>): ReactNode {
  return text.split(/(\{\w+\})/).map((piece, i) => {
    const key = piece.match(/^\{(\w+)\}$/)?.[1];
    return <Fragment key={i}>{key && key in parts ? parts[key] : piece}</Fragment>;
  });
}

const strong = (children: ReactNode) => <span className="font-semibold text-brand-dark">{children}</span>;

export default function PoAckPage() {
  const { t, lang } = useT();
  const errorText = useErrorText();
  const params = useParams<{ token: string }>();
  const token = decodeURIComponent(Array.isArray(params.token) ? params.token[0] : params.token);
  const [state, setState] = useState<PoAckStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const started = useRef(false);

  useEffect(() => {
    if (started.current) return; // React strict mode runs effects twice in dev
    started.current = true;
    publicPoAck(token, "GET")
      .then(setState)
      .catch((e: Error) => setError(e.message || "This link could not be processed."));
  }, [token]);

  const acknowledge = () => {
    setBusy(true);
    publicPoAck(token, "POST")
      .then(setState)
      .catch((e: Error) => setError(e.message || "This link could not be processed."))
      .finally(() => setBusy(false));
  };

  const po = state ? strong(`PO ${state.po_ref ?? ""}`) : null;
  const when = state ? strong(fmtAckTime(state, lang)) : null;

  return (
    <div className="flex min-h-screen items-center justify-center bg-brand-surface px-4 py-10">
      <div className="w-full max-w-md rounded-2xl border border-brand-border bg-card p-6 shadow-sm">
        <div className="flex items-start justify-between gap-3">
          <LogoLockup subtitle={t("Purchase order acknowledgement")} />
          <LanguageToggle />
        </div>

        <div className="mt-6">
          {!state && !error && (
            <div className="flex items-center gap-2 text-sm text-brand-muted" role="status">
              <Loader2 size={16} className="animate-spin" /> {t("Loading…")}
            </div>
          )}

          {error && (
            <div className="flex gap-3" role="alert">
              <AlertTriangle size={22} className="mt-0.5 shrink-0 text-signal-red" />
              <div>
                <h1 className="text-base font-semibold text-brand-dark">{t("Link not valid")}</h1>
                <p className="mt-1 text-sm text-brand-muted">{errorText(error)}</p>
                <p className="mt-3 text-xs text-brand-muted">
                  {t("Please reply to the follow-up email or contact your buyer to acknowledge this PO.")}
                </p>
              </div>
            </div>
          )}

          {state && !error && !state.acknowledged && (
            <div>
              <h1 className="text-base font-semibold text-brand-dark">
                {state.po_ref ? t("Acknowledge PO {ref}", { ref: state.po_ref }) : t("Acknowledge PO")}
              </h1>
              <p className="mt-1 text-sm text-brand-muted">
                {state.supplier_name ? <>{t("For {supplier}.", { supplier: state.supplier_name })} </> : null}
                {t("Press the button to confirm you received this purchase order. Your buyer will be notified.")}
              </p>
              <button
                type="button"
                onClick={acknowledge}
                disabled={busy}
                className="mt-4 inline-flex items-center gap-2 rounded-lg bg-emerald-600 px-4 py-2 text-sm font-semibold text-white hover:bg-emerald-700 disabled:opacity-60"
              >
                {busy ? <Loader2 size={16} className="animate-spin" /> : <CheckCircle2 size={16} />}
                {t("Acknowledge PO")}
              </button>
            </div>
          )}

          {state && !error && state.acknowledged && (
            <div className="flex gap-3" role="status">
              <CheckCircle2 size={24} className="mt-0.5 shrink-0 text-emerald-600" />
              <div className="min-w-0">
                <h1 className="text-base font-semibold text-brand-dark">
                  {state.created ? t("Thank you — PO acknowledged") : t("PO already acknowledged")}
                </h1>
                <p className="mt-1 text-sm text-brand-muted">
                  {state.created
                    ? state.supplier_name
                      ? rich(t("{po} was acknowledged by {supplier} on {when}. Your buyer has been notified."), {
                          po,
                          when,
                          supplier: state.supplier_name,
                        })
                      : rich(t("{po} was acknowledged on {when}. Your buyer has been notified."), { po, when })
                    : rich(t("{po} was already acknowledged on {when}. Nothing more is needed."), { po, when })}
                </p>
                <p className="mt-3 text-xs text-brand-muted">
                  {t(
                    "Acknowledging confirms you received the order. Please still enter committed dispatch dates in the supplier portal.",
                  )}
                </p>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
