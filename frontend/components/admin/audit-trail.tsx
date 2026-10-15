"use client";

import { Check, Copy, ScrollText, Search, SearchX, ShieldAlert, ShieldCheck, SlidersHorizontal, X } from "lucide-react";
import { useEffect, useId, useRef, useState } from "react";

import { AuditAsk } from "@/components/admin/audit-ask";
import { RecordDetail } from "@/components/admin/audit-record";
import { Disclosure } from "@/components/disclosure";
import { EmptyState } from "@/components/empty-state";
import { InfoTip } from "@/components/info-tip";
import { StatusChip } from "@/components/status-chip";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { searchAudit, verifyAuditChain } from "@/lib/api/client";
import { ApiError, BackendUnreachableError, NotSignedInError } from "@/lib/api/errors";
import {
  type AuditFilters,
  type AuditPage,
  type AuditRecord,
  EVENT_TYPES,
  NO_FILTERS,
  SOURCES,
  type VerifyResult,
  eventLabel,
  filterChips,
  moreFiltersCount,
  outcomes,
  pageUrl,
  rowText,
  summarise,
  toApiQuery,
  withoutFilter,
} from "@/lib/audit";
import { formatExact } from "@/lib/format";
import { cn } from "@/lib/utils";

// /admin/audit (ADR-007): search the company's audit trail, read each record
// in a dialog, verify the hash chain, and ask the trail in plain language (ADR-013). Admins only: the admin layout hides the page
// from others, and the backend returns 403 to them anyway. Every search and
// every verification is itself recorded in the trail.

const PAGE_SIZE = 50;
const ANY = "any"; // Select items can't have an empty value

/** What to tell the admin when a call fails. Signed out: back to /login, like the chat. */
function failureOf(error: unknown): string {
  if (error instanceof NotSignedInError) {
    window.location.assign("/login");
    return "Your session has ended.";
  }
  if (error instanceof BackendUnreachableError) return "Can't reach the server. Please try again in a moment.";
  if (error instanceof ApiError && error.status === 403) return "Only admins can read the audit trail.";
  if (error instanceof ApiError && error.status === 422) return `Check the filters: ${error.detail}`;
  if (error instanceof ApiError) return `Something went wrong (HTTP ${error.status}).`;
  return "Something went wrong.";
}

function Field({ label, children, className }: { label: string; children: React.ReactNode; className?: string }) {
  return (
    <label className={cn("grid gap-1 text-xs font-medium text-muted-foreground", className)}>
      {label}
      {children}
    </label>
  );
}

/**
 * A labelled dropdown. Not wrapped in <label> like the inputs: the Select hides a native
 * <select> inside, whose options would become part of the label a screen reader reads.
 */
function SelectField({
  label,
  value,
  onChange,
  options,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  options: { value: string; label: string }[];
}) {
  const id = useId();
  return (
    <div className="grid gap-1 text-xs font-medium text-muted-foreground">
      <span id={id}>{label}</span>
      <Select value={value} onValueChange={onChange}>
        <SelectTrigger className="w-full" aria-labelledby={id}>
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {options.map((o) => (
            <SelectItem key={o.value} value={o.value}>
              {o.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );
}

/**
 * The filter bar: who and when in view, the rest behind "More filters". Searching is explicit (Search, or
 * Enter): the backend records every search in the trail, so typing must not send one per key.
 */
function Filters({
  value,
  applied,
  onChange,
  onSearch,
  onApply,
  busy,
}: {
  value: AuditFilters;
  applied: AuditFilters;
  onChange: (next: AuditFilters) => void;
  onSearch: () => void;
  onApply: (filters: AuditFilters) => void;
  busy: boolean;
}) {
  const set = (key: keyof AuditFilters) => (event: React.ChangeEvent<HTMLInputElement>) =>
    onChange({ ...value, [key]: event.target.value });
  const [moreOpen, setMoreOpen] = useState(false);
  const more = moreFiltersCount(value);
  const chips = filterChips(applied);
  return (
    <div className="grid gap-3">
      <form
        role="search"
        aria-label="Audit trail"
        className="flex flex-wrap items-end gap-2"
        onSubmit={(event) => {
          event.preventDefault();
          onSearch();
        }}
      >
        <Field label="User (email)" className="min-w-56 flex-1">
          <div className="relative">
            <Search aria-hidden="true" className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground" />
            <Input value={value.user} onChange={set("user")} placeholder="name@company.com" autoComplete="off" className="pl-8" />
          </div>
        </Field>
        <Field label="From">
          <Input type="date" value={value.from} onChange={set("from")} className="w-40" />
        </Field>
        <Field label="To (inclusive)">
          <Input type="date" value={value.to} onChange={set("to")} className="w-40" />
        </Field>
        <Popover open={moreOpen} onOpenChange={setMoreOpen}>
          <PopoverTrigger asChild>
            <Button type="button" variant="outline">
              <SlidersHorizontal aria-hidden="true" />
              More filters
              {more ? (
                <span className="rounded-full bg-primary px-1.5 text-xs text-primary-foreground tabular-nums">
                  {more}
                  <span className="sr-only"> set</span>
                </span>
              ) : null}
            </Button>
          </PopoverTrigger>
          <PopoverContent align="end" className="grid w-80 gap-3">
            <SelectField
              label="Event"
              value={value.event_type || ANY}
              onChange={(v) => onChange({ ...value, event_type: v === ANY ? "" : v })}
              options={[{ value: ANY, label: "Any event" }, ...EVENT_TYPES]}
            />
            <SelectField
              label="Tool"
              value={value.source || ANY}
              onChange={(v) => onChange({ ...value, source: v === ANY ? "" : v, scope_id: v === ANY ? "" : value.scope_id })}
              options={[{ value: ANY, label: "Any tool" }, ...SOURCES]}
            />
            <Field label="Channel, folder, project or space ID">
              <Input
                value={value.scope_id}
                onChange={set("scope_id")}
                disabled={!value.source}
                placeholder={value.source ? "e.g. C_ENG" : "Pick a tool first"}
                autoComplete="off"
              />
            </Field>
            <Field label="Document">
              <Input value={value.document} onChange={set("document")} placeholder="e.g. drive:D_SALARY" autoComplete="off" />
            </Field>
            <Button
              type="button"
              disabled={busy}
              onClick={() => {
                setMoreOpen(false);
                onSearch();
              }}
            >
              Search
            </Button>
          </PopoverContent>
        </Popover>
        <Button type="submit" disabled={busy}>
          Search
        </Button>
      </form>
      {chips.length ? (
        <ul aria-label="Active filters" className="flex flex-wrap items-center gap-1.5">
          {chips.map((chip) => (
            <li key={chip.key}>
              <button
                type="button"
                onClick={() => onApply(withoutFilter(applied, chip.key))}
                disabled={busy}
                aria-label={`Remove filter ${chip.label}`}
                className="inline-flex h-7 cursor-pointer items-center gap-1 rounded-full border bg-secondary pr-1.5 pl-2.5 text-xs font-medium text-secondary-foreground transition-colors hover:bg-[color-mix(in_oklch,var(--secondary),var(--foreground)_8%)] active:bg-[color-mix(in_oklch,var(--secondary),var(--foreground)_14%)] disabled:opacity-50"
              >
                {chip.label}
                <X aria-hidden="true" className="size-3.5" />
              </button>
            </li>
          ))}
          <li>
            <Button variant="ghost" size="sm" onClick={() => onApply(NO_FILTERS)} disabled={busy}>
              Clear filters
            </Button>
          </li>
        </ul>
      ) : null}
    </div>
  );
}

/** The hash chain, as a status card: not checked yet, intact, or broken (with a way to that record). */
function VerifyPanel({ onOpenRecord }: { onOpenRecord: (id: number) => void }) {
  const [state, setState] = useState<
    { status: "idle" | "running" } | { status: "done"; result: VerifyResult; at: string } | { status: "failed"; message: string }
  >({ status: "idle" });
  const [copied, setCopied] = useState(false);

  async function verify() {
    setState({ status: "running" });
    setCopied(false);
    try {
      setState({ status: "done", result: await verifyAuditChain(), at: new Date().toISOString() });
    } catch (error) {
      setState({ status: "failed", message: failureOf(error) });
    }
  }

  async function copy(hash: string) {
    try {
      await navigator.clipboard.writeText(hash);
      setCopied(true);
    } catch {
      setCopied(false);
    }
  }

  const result = state.status === "done" ? state.result : null;
  const broken = result && !result.ok;
  return (
    <section
      aria-labelledby="chain-heading"
      className={cn(
        "grid gap-3 rounded-xl bg-card p-4 ring-1 ring-foreground/10",
        broken && "ring-destructive/40",
      )}
    >
      <div className="flex flex-wrap items-center gap-3">
        <span
          className={cn(
            "grid size-9 shrink-0 place-items-center rounded-lg bg-muted text-muted-foreground",
            result?.ok && "bg-success text-success-foreground",
            broken && "bg-destructive/10 text-destructive",
          )}
        >
          {broken ? <ShieldAlert aria-hidden="true" className="size-5" /> : <ShieldCheck aria-hidden="true" className="size-5" />}
        </span>
        <div className="grid min-w-0 flex-1 gap-0.5">
          <h2 id="chain-heading" className="flex items-center gap-1 text-sm font-semibold">
            Hash chain
            <InfoTip label="About the hash chain">
              Each record holds the hash of the one before it, so a changed, deleted or reordered record shows when the
              chain is verified.
            </InfoTip>
          </h2>
          <p aria-live="polite" className="text-sm text-muted-foreground">
            {state.status === "idle" ? "Not verified on this visit." : null}
            {state.status === "running" ? "Verifying…" : null}
            {state.status === "failed" ? <span className="text-destructive">{state.message}</span> : null}
            {result?.ok ? (
              <>
                <StatusChip tone="success" className="mr-1.5 align-middle">
                  <Check aria-hidden="true" />
                  Intact
                </StatusChip>
                {result.checked} {result.checked === 1 ? "record" : "records"} checked: none changed, deleted or
                reordered.
              </>
            ) : null}
            {broken ? (
              <>
                <StatusChip tone="danger" className="mr-1.5 align-middle">
                  <X aria-hidden="true" />
                  Broken at #{result.first_broken_id}
                </StatusChip>
                {result.reason}
              </>
            ) : null}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          {broken && result.first_broken_id !== null ? (
            <Button variant="outline" size="sm" onClick={() => onOpenRecord(result.first_broken_id!)}>
              Open record #{result.first_broken_id}
            </Button>
          ) : null}
          <Button
            variant="outline"
            size="sm"
            onClick={verify}
            disabled={state.status === "running"}
            aria-busy={state.status === "running"}
          >
            <ShieldCheck aria-hidden="true" />
            {state.status === "running" ? "Verifying…" : state.status === "done" ? "Verify again" : "Verify chain"}
          </Button>
        </div>
      </div>
      {result?.ok && result.head ? (
        <Disclosure summary={`Latest record #${result.head.id} and its hash`}>
          <div className="grid gap-2 text-muted-foreground">
            <p>Note this hash outside KnowBuddy: if anyone rewrote the whole log, it would no longer match.</p>
            <div className="flex flex-wrap items-center gap-2">
              <code className="rounded bg-muted px-1.5 py-0.5 text-xs break-all text-foreground">{result.head.hash}</code>
              <Button variant="outline" size="sm" onClick={() => copy(result.head!.hash)}>
                {copied ? <Check aria-hidden="true" /> : <Copy aria-hidden="true" />}
                {copied ? "Copied" : "Copy hash"}
              </Button>
            </div>
          </div>
        </Disclosure>
      ) : null}
    </section>
  );
}

type Results =
  | { status: "loading" }
  | { status: "failed"; message: string }
  | { status: "ready"; records: AuditRecord[]; nextBeforeId: number | null };

export function AuditTrail({
  initialFilters,
  initialRecordId,
}: {
  initialFilters: AuditFilters;
  initialRecordId: number | null; // ?record=N: open that record on arrival
}) {
  const [draft, setDraft] = useState(initialFilters); // what the form shows
  // What the results are for. `n` counts searches: searching again with the same filters is a new search.
  const [search, setSearch] = useState({ filters: initialFilters, n: 0 });
  const applied = search.filters;
  const [results, setResults] = useState<Results>({ status: "loading" });
  const [loadingMore, setLoadingMore] = useState(false);
  const [moreError, setMoreError] = useState<string | null>(null);
  const [selected, setSelected] = useState<AuditRecord | null>(null);
  const [openError, setOpenError] = useState<string | null>(null);
  // Return focus to whatever opened the record dialog (keyboard users).
  const opener = useRef<HTMLElement | null>(null);
  // Opening a record adds a browser history entry (?record=N), so Back closes it.
  // True while the open record is the one we added.
  const pushed = useRef(false);
  // The request for search `n`. In development React runs this effect twice on mount; the second run
  // reuses the request instead of sending another, since the backend audits every search.
  const inflight = useRef<{ n: number; promise: Promise<AuditPage> } | null>(null);

  useEffect(() => {
    let current = true;
    setResults({ status: "loading" });
    setMoreError(null);
    if (inflight.current?.n !== search.n) {
      inflight.current = { n: search.n, promise: searchAudit(toApiQuery(search.filters, { limit: PAGE_SIZE })) };
    }
    inflight.current.promise.then(
      (page) => current && setResults({ status: "ready", records: page.records, nextBeforeId: page.next_before_id }),
      (error) => current && setResults({ status: "failed", message: failureOf(error) }),
    );
    return () => {
      current = false; // a newer search replaced this one
    };
  }, [search]);

  function apply(filters: AuditFilters) {
    setDraft(filters);
    setSearch((s) => ({ filters: { ...filters }, n: s.n + 1 }));
    // Keep the filters in the URL, so a view can be bookmarked or shared (Next.js syncs its router with this).
    window.history.replaceState(null, "", pageUrl(filters));
  }

  /** Show a record in the dialog, with its number in the URL (a new history entry, so Back closes it). */
  function show(record: AuditRecord) {
    setSelected(record);
    window.history[pushed.current ? "replaceState" : "pushState"](null, "", pageUrl(applied, record.id));
    pushed.current = true;
  }

  function close() {
    setSelected(null);
    if (pushed.current) {
      pushed.current = false;
      window.history.back(); // removes the entry show() added
    } else {
      window.history.replaceState(null, "", pageUrl(applied)); // arrived with ?record=N
    }
  }

  async function loadOlder() {
    if (results.status !== "ready" || results.nextBeforeId === null) return;
    setLoadingMore(true);
    setMoreError(null);
    try {
      const page = await searchAudit(toApiQuery(applied, { beforeId: results.nextBeforeId, limit: PAGE_SIZE }));
      setResults({ status: "ready", records: [...results.records, ...page.records], nextBeforeId: page.next_before_id });
    } catch (error) {
      setMoreError(failureOf(error));
    } finally {
      setLoadingMore(false);
    }
  }

  /**
   * Open one record by number ("chain broken at #N", or ?record=N in the URL): the newest
   * record below N + 1. `fromUrl`: the URL already says ?record=N, so add no history entry.
   */
  async function openRecord(id: number, fromUrl = false) {
    opener.current = document.activeElement as HTMLElement | null;
    setOpenError(null);
    try {
      const [record] = (await searchAudit(toApiQuery(NO_FILTERS, { beforeId: id + 1, limit: 1 }))).records;
      if (record?.id !== id) setOpenError(`Record #${id} isn't in your company's trail.`);
      else if (fromUrl) setSelected(record);
      else show(record);
    } catch (error) {
      setOpenError(failureOf(error));
    }
  }

  // Arriving with ?record=N opens that record.
  const opened = useRef(false);
  useEffect(() => {
    if (initialRecordId !== null && !opened.current) {
      opened.current = true; // once, even when React runs effects twice in development
      void openRecord(initialRecordId, true);
    }
  }, []); // on arrival only

  // Back (or Forward) to a URL without ?record closes the dialog.
  useEffect(() => {
    function onPopState() {
      if (!new URLSearchParams(window.location.search).has("record")) {
        pushed.current = false;
        setSelected(null);
      }
    }
    window.addEventListener("popstate", onPopState);
    return () => window.removeEventListener("popstate", onPopState);
  }, []);

  const records = results.status === "ready" ? results.records : [];
  const filtered = filterChips(applied).length > 0;
  const filtersRef = useRef<HTMLDivElement>(null);

  return (
    <div className="grid gap-6">
      <VerifyPanel onOpenRecord={openRecord} />
      <AuditAsk
        onOpenRecord={openRecord}
        onOpenInTrail={(filters) => {
          apply(filters);
          filtersRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
        }}
        describeError={failureOf}
      />
      {openError ? (
        <p role="alert" className="text-sm text-destructive">
          {openError}
        </p>
      ) : null}
      <div ref={filtersRef} className="scroll-mt-4">
        <Filters
          value={draft}
          applied={applied}
          onChange={setDraft}
          onSearch={() => apply(draft)}
          onApply={apply}
          busy={results.status === "loading"}
        />
      </div>
      <p className="sr-only" aria-live="polite">
        {results.status === "ready" ? `${records.length} records shown` : ""}
      </p>
      {results.status === "failed" ? (
        <Alert variant="destructive">
          <ShieldAlert aria-hidden="true" />
          <AlertTitle>Couldn&apos;t load the audit trail</AlertTitle>
          <AlertDescription>{results.message}</AlertDescription>
        </Alert>
      ) : results.status === "ready" && records.length === 0 ? (
        <div className="rounded-xl ring-1 ring-foreground/10">
          {filtered ? (
            <EmptyState
              icon={SearchX}
              title="No records match these filters"
              description="Try a wider date range, or remove a filter."
              action={
                <Button variant="outline" onClick={() => apply(NO_FILTERS)}>
                  Clear filters
                </Button>
              }
            />
          ) : (
            <EmptyState
              icon={ScrollText}
              title="No records yet"
              description="Questions, boundary changes and connections appear here as they happen."
            />
          )}
        </div>
      ) : (
        <div className="overflow-x-auto rounded-xl bg-card ring-1 ring-foreground/10">
          {/* Fixed columns: a long question truncates instead of pushing its outcome out of view. */}
          <Table className="min-w-[44rem] table-fixed">
            <TableHeader>
              <TableRow>
                <TableHead className="w-40">Time</TableHead>
                <TableHead className="w-44">User</TableHead>
                <TableHead>What</TableHead>
                <TableHead className="w-16 text-right">Ref</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {results.status === "loading"
                ? [0, 1, 2].map((i) => (
                    <TableRow key={i}>
                      <TableCell colSpan={4}>
                        <Skeleton className="h-5 w-full" />
                      </TableCell>
                    </TableRow>
                  ))
                : null}
              {records.map((record) => (
                <TableRow
                  key={record.id}
                  // The row's button stretches over the whole row (after:inset-0), so anywhere on it opens the record.
                  className="relative cursor-pointer"
                >
                  <TableCell className="whitespace-nowrap text-muted-foreground tabular-nums">{formatExact(record.ts)}</TableCell>
                  <TableCell className="truncate" title={record.user_email ?? undefined}>
                    {record.user_email ?? "no user"}
                  </TableCell>
                  <TableCell>
                    <div className="flex min-w-0 items-center gap-2">
                      <StatusChip>{eventLabel(record.event_type)}</StatusChip>
                      <button
                        type="button"
                        onClick={(event) => {
                          opener.current = event.currentTarget;
                          show(record);
                        }}
                        aria-label={`Record #${record.id}: ${summarise(record)}`}
                        className="min-w-0 flex-1 cursor-pointer truncate text-left outline-none after:absolute after:inset-0 focus-visible:after:rounded-sm focus-visible:after:ring-2 focus-visible:after:ring-ring"
                      >
                        {rowText(record)}
                      </button>
                      {outcomes(record).map((o) => (
                        <StatusChip key={o.text} tone={o.tone}>
                          {o.text}
                        </StatusChip>
                      ))}
                    </div>
                  </TableCell>
                  <TableCell className="text-right text-muted-foreground tabular-nums">#{record.id}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
      {results.status === "ready" && results.nextBeforeId !== null ? (
        <div className="grid justify-items-center gap-2">
          <Button variant="outline" onClick={loadOlder} disabled={loadingMore} aria-busy={loadingMore}>
            {loadingMore ? "Loading…" : "Load older"}
          </Button>
          {moreError ? (
            <p role="alert" className="text-sm text-destructive">
              {moreError}
            </p>
          ) : null}
        </div>
      ) : null}
      <Dialog open={selected !== null} onOpenChange={(open) => !open && close()}>
        <DialogContent
          className="max-h-[85vh] overflow-y-auto sm:max-w-2xl"
          // Focus the dialog itself on opening (screen readers announce its title), not its first button,
          // which would be an ⓘ and pop its explanation open.
          onOpenAutoFocus={(event) => {
            event.preventDefault();
            (event.currentTarget as HTMLElement).focus();
          }}
          onCloseAutoFocus={(event) => {
            event.preventDefault();
            opener.current?.focus();
          }}
        >
          <DialogHeader className="pr-8">
            <DialogTitle className="text-xl font-semibold">Audit record #{selected?.id}</DialogTitle>
            {/* For screen readers only: a dialog needs a description, the content says the rest. */}
            <DialogDescription className="sr-only">{selected ? summarise(selected) : null}</DialogDescription>
          </DialogHeader>
          {selected ? <RecordDetail record={selected} /> : null}
        </DialogContent>
      </Dialog>
    </div>
  );
}
