import { Check, Eye, EyeOff, ShieldAlert, X } from "lucide-react";
import type { ReactNode } from "react";

import { InfoTip } from "@/components/info-tip";
import { Badge } from "@/components/ui/badge";
import {
  type AuditRecord,
  type DocumentRow,
  type QueryPayload,
  documentRows,
  eventLabel,
  formatMs,
  hasMaskedValues,
  liveCheckLabel,
  searchLabel,
  timingRows,
} from "@/lib/audit";
import { formatExact } from "@/lib/format";

// The content of one audit record's dialog on /admin/audit (ADR-007). Explanations live behind ⓘ
// buttons, not in headings; per-document facts are one table.

function Section({ title, info, children }: { title: string; info?: ReactNode; children: ReactNode }) {
  return (
    <section className="grid gap-2 border-t pt-4">
      {/* The ⓘ sits beside the heading, not in it, so the heading's name stays just the title. */}
      <div className="flex items-center gap-1">
        <h3 className="text-xs font-semibold tracking-wide text-foreground uppercase">{title}</h3>
        {info}
      </div>
      {children}
    </section>
  );
}

/** A label/value table: one row per fact, light lines between rows. */
function FactTable({ rows }: { rows: [string, ReactNode][] }) {
  return (
    <table className="w-full text-sm">
      <tbody>
        {rows.map(([label, value]) => (
          <tr key={label} className="border-b last:border-0">
            <th scope="row" className="w-28 py-1.5 pr-4 text-left align-top font-normal text-muted-foreground">
              {label}
            </th>
            <td className="py-1.5 break-words">{value}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

/** Allowed in green with ✓, denied in red with ✗. The words stay: colour and icons alone don't carry it. */
function Decision({ allowed }: { allowed: boolean }) {
  return allowed ? (
    <Badge variant="success">
      <Check aria-hidden="true" />
      allowed
    </Badge>
  ) : (
    <Badge variant="destructive">
      <X aria-hidden="true" />
      denied
    </Badge>
  );
}

function kinds(masked: Record<string, number>): string {
  return Object.entries(masked)
    .filter(([, n]) => n > 0)
    .map(([kind, n]) => `${kind} ${n}`)
    .join(", ");
}

function Note({ icon, text, info, label }: { icon: ReactNode; text: string; info: ReactNode; label: string }) {
  return (
    <span className="inline-flex items-center gap-1 text-xs whitespace-nowrap text-muted-foreground">
      {icon}
      {text}
      <InfoTip label={label}>{info}</InfoTip>
    </span>
  );
}

function DocumentNotes({ row }: { row: DocumentRow }) {
  const masked = row.masked ? Object.values(row.masked).reduce((sum, n) => sum + n, 0) : 0;
  return (
    <div className="flex flex-wrap gap-x-3 gap-y-1">
      {masked ? (
        <Note
          icon={<EyeOff aria-hidden="true" className="size-3.5" />}
          text={`${masked} masked`}
          label="About the masked values"
          info={`Personal data or secrets hidden from this person (Need-to-Know Shield): ${kinds(row.masked!)}.`}
        />
      ) : null}
      {row.handler ? (
        <Note
          icon={<Eye aria-hidden="true" className="size-3.5" />}
          text="shown in full"
          label="About shown in full"
          info="This person handles this item in the tool (e.g. its owner), so nothing in it was masked for them."
        />
      ) : null}
      {row.injection ? (
        <Note
          icon={<ShieldAlert aria-hidden="true" className="size-3.5" />}
          text={`${row.injection.removed} instruction${row.injection.removed === 1 ? "" : "s"} removed`}
          label="About the removed instructions"
          info={`A line written to the AI, not to people, was removed before the AI read this document. Matched: ${row.injection.rules.join(", ")}.`}
        />
      ) : null}
    </div>
  );
}

function DocumentsTable({ rows }: { rows: DocumentRow[] }) {
  if (!rows.length) return <p className="text-sm text-muted-foreground">None</p>;
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b text-left text-xs text-muted-foreground">
            <th scope="col" className="py-1.5 pr-3 font-normal">Document</th>
            <th scope="col" className="py-1.5 pr-3 font-normal">Decision</th>
            <th scope="col" className="py-1.5 pr-3 font-normal">Sent</th>
            <th scope="col" className="py-1.5 font-normal">Notes</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.document} className="border-b align-top last:border-0">
              <td className="py-2 pr-3">
                <code className="text-xs break-all">{row.document}</code>
              </td>
              <td className="py-2 pr-3">
                <div className="grid justify-items-start gap-1">
                  <Decision allowed={row.allowed} />
                  {row.reason ? <span className="text-xs text-muted-foreground">{row.reason}</span> : null}
                </div>
              </td>
              <td className="py-2 pr-3 text-xs whitespace-nowrap tabular-nums">
                {row.sentAs ? (
                  <>
                    <span className="font-semibold">S{row.sentAs}</span>
                    {row.cited ? <span className="text-muted-foreground"> · cited</span> : null}
                  </>
                ) : (
                  <span className="text-muted-foreground" aria-label="not sent">
                    —
                  </span>
                )}
              </td>
              <td className="py-2">
                <DocumentNotes row={row} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

const MASKED_INFO = "Some values are masked: the audit trail keeps no personal data or secrets (Need-to-Know Shield).";

/** A quiet line under a section, with an ⓘ. */
function QuietLine({ text, label, info }: { text: string; label: string; info: ReactNode }) {
  return (
    <p className="flex items-center gap-1 text-xs text-muted-foreground">
      {text}
      <InfoTip label={label}>{info}</InfoTip>
    </p>
  );
}

function QueryDetail({ record, p }: { record: AuditRecord; p: QueryPayload }) {
  const live = liveCheckLabel(p.live_check_mode);
  const timings = timingRows(p.timings_ms);
  const answerMasked = p.answer_masked ? kinds(p.answer_masked) : "";
  return (
    <>
      <FactTable
        rows={[
          ["Who", record.user_email ?? "no user"],
          ["When", <span className="tabular-nums">{formatExact(record.ts)}</span>],
          ["Event", eventLabel(record.event_type)],
          ["Role", p.role === "admin" ? "Admin" : p.role === "user" ? "User" : "unknown"],
          [
            "Search",
            <span className="inline-flex items-center gap-1">
              {searchLabel(p.search_mode)}
              <InfoTip label="About the search">
                Keyword search matches the question&apos;s words; meaning search matches what it&apos;s about. &quot;Keyword
                only&quot; means the meaning search was unavailable.
              </InfoTip>
            </span>,
          ],
          [
            "Live check",
            <span className="inline-flex items-center gap-1">
              {live.text}
              {live.kind === "other" ? null : (
                <InfoTip label="About the live check">
                  {live.kind === "live"
                    ? "Each tool was asked, as this person, whether they can still read each document."
                    : "A seeded demo user with no connected tools: checked against the permissions saved in KnowBuddy, not asked live from each tool."}
                </InfoTip>
              )}
            </span>,
          ],
          ["LLM", p.llm_error ? `failed (${p.llm_error})` : p.llm_called ? (p.model ?? "called") : "not called"],
        ]}
      />
      {timings.length ? (
        <Section
          title="Timings"
          info={
            <InfoTip label="About the timings">
              <strong>Embed:</strong> turning the question into numbers for the meaning search. <strong>Search:</strong>{" "}
              finding matching documents, filtered by permission. <strong>Live check:</strong> asking each tool whether
              this person can still read them. <strong>LLM:</strong> the AI writing the answer. <strong>Total:</strong>{" "}
              start to finish, including the audit record.
            </InfoTip>
          }
        >
          <table className="w-full max-w-xs text-sm">
            <tbody>
              {timings.map((t) => (
                <tr key={t.step} className={t.total ? "border-t font-semibold" : undefined}>
                  <th scope="row" className={`py-1 pr-4 text-left ${t.total ? "font-semibold" : "font-normal"}`}>
                    {t.step}
                  </th>
                  <td className="py-1 text-right tabular-nums">{formatMs(t.ms)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Section>
      ) : null}
      <Section
        title="Question"
        info={hasMaskedValues(p.question) ? <InfoTip label="About the masked values">{MASKED_INFO}</InfoTip> : null}
      >
        <p className="text-sm whitespace-pre-wrap">{p.question}</p>
        {p.injection?.question.length ? (
          <QuietLine
            text="Looked like an attempt to instruct the AI"
            label="About the instruction attempt"
            info={`The question matched: ${p.injection.question.join(", ")}. It can't widen what is searched or shown; it's recorded for review.`}
          />
        ) : null}
      </Section>
      <Section
        title="Documents"
        info={
          <InfoTip label="About the documents">
            Every document the question matched. Allowed ones may be sent to the AI, as S1, S2… in the answer; denied
            ones never reach it.
          </InfoTip>
        }
      >
        <DocumentsTable rows={documentRows(p)} />
      </Section>
      <Section
        title="Answer"
        info={hasMaskedValues(p.answer) ? <InfoTip label="About the masked values">{MASKED_INFO}</InfoTip> : null}
      >
        <p className="text-sm whitespace-pre-wrap">{p.answer}</p>
        {answerMasked ? (
          <QuietLine
            text="Values masked in the answer"
            label="About the answer check"
            info={`The answer was checked again before it was shown: values this person wasn't shown in the sources were masked (${answerMasked}).`}
          />
        ) : null}
        {p.removed_links ? (
          <QuietLine
            text={`${p.removed_links} link${p.removed_links === 1 ? "" : "s"} removed from the answer`}
            label="About the removed links"
            info="Links the AI wasn't shown in the sources are removed, so an answer can't send people to a made-up address."
          />
        ) : null}
        {p.removed_citations?.length ? (
          <QuietLine
            text={`Invented citations removed: ${p.removed_citations.join(", ")}`}
            label="About the removed citations"
            info="The AI cited a source label it wasn't given; the citation was removed."
          />
        ) : null}
      </Section>
    </>
  );
}

function OtherDetail({ record }: { record: AuditRecord }) {
  return (
    <FactTable
      rows={[
        ["Who", record.user_email ?? "no user"],
        ["When", <span className="tabular-nums">{formatExact(record.ts)}</span>],
        ["Event", eventLabel(record.event_type)],
        ...Object.entries(record.payload).map(
          ([key, value]) => [key, typeof value === "string" ? value : JSON.stringify(value)] as [string, ReactNode],
        ),
      ]}
    />
  );
}

/** One audit record, as the dialog shows it. */
export function RecordDetail({ record }: { record: AuditRecord }) {
  return (
    <div className="grid gap-5">
      {record.event_type === "query" ? (
        <QueryDetail record={record} p={record.payload as QueryPayload} />
      ) : (
        <OtherDetail record={record} />
      )}
      <Section title="Hash chain">
        <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-xs">
          <dt className="text-muted-foreground">Previous</dt>
          <dd>
            <code className="break-all">{record.prev_hash}</code>
          </dd>
          <dt className="text-muted-foreground">This</dt>
          <dd>
            <code className="break-all">{record.hash}</code>
          </dd>
        </dl>
      </Section>
      <details className="text-sm">
        <summary className="cursor-pointer text-muted-foreground">Raw record</summary>
        <pre className="mt-2 overflow-x-auto rounded bg-muted p-3 text-xs">{JSON.stringify(record, null, 2)}</pre>
      </details>
    </div>
  );
}
