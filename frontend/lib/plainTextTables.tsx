/**
 * Plain-text mail bodies with markdown-style pipe tables.
 *
 * Older follow-up mails were stored as plain text only, with their material
 * table written as pipe rows:
 *
 *   | Sr No | CRM No | Material Name | PO Qty |
 *   | --- | --- | --- | --- |
 *   | 1 | 2627-018961 | WORK SUPPORT ... | 1 |
 *
 * Shown verbatim, that is unreadable. `PlainTextWithTables` renders such runs
 * as a real table and keeps every other line as plain text. It builds React
 * elements only — no HTML string is ever injected — so untrusted mail text
 * stays inert.
 */

export type TextBlock =
  | { kind: "text"; text: string }
  | { kind: "table"; header: string[]; rows: string[][] };

function splitRow(line: string): string[] {
  let t = line.trim();
  if (t.startsWith("|")) t = t.slice(1);
  if (t.endsWith("|")) t = t.slice(0, -1);
  return t.split("|").map((c) => c.trim());
}

/** A line that looks like a table row: starts with a pipe, or has 2+ pipes. */
function isPipeRow(line: string): boolean {
  const t = line.trim();
  if (!t.includes("|")) return false;
  const pipes = (t.match(/\|/g) || []).length;
  return (t.startsWith("|") || pipes >= 2) && splitRow(t).length >= 2;
}

/** The markdown header separator row: | --- | :---: | */
function isSeparatorRow(cells: string[]): boolean {
  return cells.length > 0 && cells.every((c) => /^:?-{2,}:?$/.test(c));
}

/** Split text into plain-text and table blocks. A table needs 2+ pipe rows. */
export function parsePlainTextBlocks(text: string | null | undefined): TextBlock[] {
  const lines = (text || "").replace(/\r\n?/g, "\n").split("\n");
  const blocks: TextBlock[] = [];
  let buffer: string[] = [];

  const flushText = () => {
    const joined = buffer.join("\n").replace(/^\n+|\n+$/g, "");
    if (joined.trim()) blocks.push({ kind: "text", text: joined });
    buffer = [];
  };

  let i = 0;
  while (i < lines.length) {
    if (!isPipeRow(lines[i])) {
      buffer.push(lines[i]);
      i += 1;
      continue;
    }
    let j = i;
    while (j < lines.length && isPipeRow(lines[j])) j += 1;
    const run = lines.slice(i, j).map(splitRow);
    const dataRows = run.filter((cells) => !isSeparatorRow(cells));
    if (run.length < 2 || dataRows.length === 0) {
      // A lone pipe line (e.g. a reply-format hint) stays plain text.
      buffer.push(...lines.slice(i, j));
    } else {
      flushText();
      const [header, ...rows] = dataRows;
      const width = Math.max(header.length, ...rows.map((r) => r.length));
      const pad = (r: string[]) => [...r, ...Array(Math.max(0, width - r.length)).fill("")];
      blocks.push({ kind: "table", header: pad(header), rows: rows.map(pad) });
    }
    i = j;
  }
  flushText();
  return blocks;
}

/** True when the text holds at least one renderable pipe table. */
export function hasPipeTable(text: string | null | undefined): boolean {
  return parsePlainTextBlocks(text).some((b) => b.kind === "table");
}

/** Cut a quoted reply chain ("On … wrote:", "> …", "-----Original Message-----"). */
export function cutQuotedReply(text: string | null | undefined): string {
  const out: string[] = [];
  for (const line of (text || "").replace(/\r\n?/g, "\n").split("\n")) {
    const t = line.trim();
    if (/^On .+ wrote:\s*$/i.test(t) || t.startsWith(">") || t === "-----Original Message-----") break;
    out.push(line);
  }
  return out.join("\n").replace(/\n{3,}/g, "\n\n").trim();
}

export function PlainTextWithTables({
  text,
  className = "",
  textClassName = "whitespace-pre-wrap break-words",
}: {
  text: string | null | undefined;
  className?: string;
  textClassName?: string;
}) {
  const blocks = parsePlainTextBlocks(text);
  return (
    <div className={className}>
      {blocks.map((b, i) =>
        b.kind === "text" ? (
          <p key={i} className={`${textClassName} ${i > 0 ? "mt-2" : ""}`}>
            {b.text}
          </p>
        ) : (
          <div key={i} className={`overflow-x-auto rounded border border-black/10 dark:border-white/15 ${i > 0 ? "mt-2" : ""}`}>
            <table className="min-w-full text-xs">
              <thead className="bg-black/5 dark:bg-white/10">
                <tr>
                  {b.header.map((h, c) => (
                    <th key={c} className="whitespace-nowrap px-2 py-1.5 text-left font-semibold">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {b.rows.map((row, r) => (
                  <tr key={r} className="border-t border-black/10 dark:border-white/10">
                    {row.map((cell, c) => (
                      <td key={c} className="px-2 py-1.5 align-top">
                        {cell || "-"}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ),
      )}
    </div>
  );
}
