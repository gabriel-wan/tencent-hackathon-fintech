"use client";

import { Check, Copy, ShieldAlert, ShieldCheck } from "lucide-react";
import { useEffect, useId, useRef, useState } from "react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { RecordDetail } from "@/components/admin/audit-record";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
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
  pageUrl,
  summarise,
  toApiQuery,
} from "@/lib/audit";
import { formatExact } from "@/lib/format";

// /admin/audit (ADR-007): search the company's audit trail, read each record,
// in a dialog, and verify the hash chain. Admins only: the admin layout hides the page
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

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="grid gap-1 text-xs font-medium text-muted-foreground">
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

function Filters({
  value,
  onChange,
  onSearch,
  onClear,
  busy,
}: {
  value: AuditFilters;
  onChange: (next: AuditFilters) => void;
  onSearch: () => void;
  onClear: () => void;
  busy: boolean;
}) {
  const set = (key: keyof AuditFilters) => (event: React.ChangeEvent<HTMLInputElement>) =>
    onChange({ ...value, [key]: event.target.value });
  return (
    <form
      role="search"
      aria-label="Audit trail"
      className="grid gap-3 sm:grid-cols-3"
      onSubmit={(event) => {
        event.preventDefault();
        onSearch();
      }}
    >
      <Field label="User (email)">
        <Input value={value.user} onChange={set("user")} placeholder="name@company.com" autoComplete="off" />
      </Field>
      <Field label="From">
        <Input type="date" value={value.from} onChange={set("from")} />
      </Field>
      <Field label="To (inclusive)">
        <Input type="date" value={value.to} onChange={set("to")} />
      </Field>
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
      <div className="flex items-end gap-2 sm:col-span-2">
        <Button type="submit" disabled={busy}>
          Search
        </Button>
        <Button type="button" variant="outline" onClick={onClear} disabled={busy}>
          Clear
        </Button>
      </div>
    </form>
  );
}

function VerifyPanel({ onOpenRecord }: { onOpenRecord: (id: number) => void }) {
  const [state, setState] = useState<
    { status: "idle" | "running" } | { status: "done"; result: VerifyResult } | { status: "failed"; message: string }
  >({ status: "idle" });
  const [copied, setCopied] = useState(false);

  async function verify() {
    setState({ status: "running" });
    setCopied(false);
    try {
      setState({ status: "done", result: await verifyAuditChain() });
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
  return (
    <div className="grid gap-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm text-muted-foreground">
          Each record holds the hash of the one before it, so a changed, deleted or reordered record shows.
        </p>
        <Button variant="outline" size="sm" onClick={verify} disabled={state.status === "running"} aria-busy={state.status === "running"}>
          <ShieldCheck aria-hidden="true" />
          {state.status === "running" ? "Verifying…" : "Verify chain"}
        </Button>
      </div>
      <div aria-live="polite">
        {state.status === "failed" ? (
          <Alert variant="destructive">
            <ShieldAlert aria-hidden="true" />
            <AlertTitle>Couldn&apos;t verify the chain</AlertTitle>
            <AlertDescription>{state.message}</AlertDescription>
          </Alert>
        ) : null}
        {result && result.ok ? (
          <Alert>
            <ShieldCheck aria-hidden="true" />
            <AlertTitle>Chain intact</AlertTitle>
            <AlertDescription>
              <p>
                {result.checked} {result.checked === 1 ? "record" : "records"} checked: none changed, deleted or
                reordered.
              </p>
              {result.head ? (
                <div className="grid gap-1.5">
                  <p>
                    Latest record #{result.head.id}. Note its hash outside KnowBuddy: if anyone rewrote the whole log,
                    it would no longer match.
                  </p>
                  <div className="flex flex-wrap items-center gap-2">
                    <code className="rounded bg-muted px-1.5 py-0.5 text-xs break-all">{result.head.hash}</code>
                    <Button variant="outline" size="sm" onClick={() => copy(result.head!.hash)}>
                      {copied ? <Check aria-hidden="true" /> : <Copy aria-hidden="true" />}
                      {copied ? "Copied" : "Copy hash"}
                    </Button>
                  </div>
                </div>
              ) : null}
            </AlertDescription>
          </Alert>
        ) : null}
        {result && !result.ok ? (
          <Alert variant="destructive">
            <ShieldAlert aria-hidden="true" />
            <AlertTitle>Chain broken at record #{result.first_broken_id}</AlertTitle>
            <AlertDescription>
              <p>{result.reason}</p>
              {result.first_broken_id !== null ? (
                <Button variant="outline" size="sm" onClick={() => onOpenRecord(result.first_broken_id!)}>
                  Open record #{result.first_broken_id}
                </Button>
              ) : null}
            </AlertDescription>
          </Alert>
        ) : null}
      </div>
    </div>
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
  return (
    <div className="grid gap-6">
      <VerifyPanel onOpenRecord={openRecord} />
      {openError ? (
        <p role="alert" className="text-sm text-destructive">
          {openError}
        </p>
      ) : null}
      <Filters
        value={draft}
        onChange={setDraft}
        onSearch={() => apply(draft)}
        onClear={() => apply(NO_FILTERS)}
        busy={results.status === "loading"}
      />
      <p className="sr-only" aria-live="polite">
        {results.status === "ready" ? `${records.length} records shown` : ""}
      </p>
      {results.status === "failed" ? (
        <Alert variant="destructive">
          <ShieldAlert aria-hidden="true" />
          <AlertTitle>Couldn&apos;t load the audit trail</AlertTitle>
          <AlertDescription>{results.message}</AlertDescription>
        </Alert>
      ) : (
        <div className="overflow-x-auto rounded-lg border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Time</TableHead>
                <TableHead>User</TableHead>
                <TableHead>What</TableHead>
                <TableHead className="text-right">Ref</TableHead>
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
              {results.status === "ready" && records.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={4} className="py-8 text-center text-muted-foreground">
                    No records match these filters.
                  </TableCell>
                </TableRow>
              ) : null}
              {records.map((record) => (
                <TableRow key={record.id}>
                  <TableCell className="whitespace-nowrap tabular-nums">{formatExact(record.ts)}</TableCell>
                  <TableCell className="max-w-48 truncate" title={record.user_email ?? undefined}>
                    {record.user_email ?? "no user"}
                  </TableCell>
                  <TableCell className="max-w-96">
                    <button
                      type="button"
                      onClick={(event) => {
                        opener.current = event.currentTarget;
                        show(record);
                      }}
                      className="block max-w-full truncate text-left text-primary underline-offset-4 hover:underline"
                    >
                      {summarise(record)}
                    </button>
                  </TableCell>
                  <TableCell className="text-right tabular-nums">#{record.id}</TableCell>
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
