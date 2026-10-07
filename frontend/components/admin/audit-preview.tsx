"use client";

import { ShieldCheck } from "lucide-react";
import { useRef, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { formatExact } from "@/lib/format";
import { MOCK_AUDIT_RECORDS, type MockAuditRecord } from "@/lib/mock/audit";

// DEVELOPMENT ONLY design preview of /admin/audit (ui-plan.md 6.3), shown
// inside <DesignPreview>. Filters and "Verify chain" are deliberately
// disabled: nothing here searches or verifies anything.

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="grid gap-1 text-xs font-medium text-muted-foreground">
      {label}
      {children}
    </label>
  );
}

function Filters() {
  return (
    <fieldset disabled className="grid gap-3 sm:grid-cols-3" aria-describedby="filters-note">
      <Field label="User">
        <Input placeholder="e.g. charlie@contractor.example" />
      </Field>
      <Field label="From">
        <Input type="date" />
      </Field>
      <Field label="To">
        <Input type="date" />
      </Field>
      <Field label="Source">
        <Select disabled>
          <SelectTrigger className="w-full">
            <SelectValue placeholder="Any" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="any">Any</SelectItem>
          </SelectContent>
        </Select>
      </Field>
      <Field label="Document">
        <Input placeholder="e.g. drive:D_Q3_INCIDENT" />
      </Field>
      <Field label="Decision">
        <Select disabled>
          <SelectTrigger className="w-full">
            <SelectValue placeholder="Any" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="any">Any</SelectItem>
          </SelectContent>
        </Select>
      </Field>
      <p id="filters-note" className="text-xs text-muted-foreground sm:col-span-3">
        Filters are not wired: they wait for <code>GET /api/admin/audit</code>.
      </p>
    </fieldset>
  );
}

function Decision({ allowed }: { allowed: boolean }) {
  return allowed ? (
    <Badge variant="secondary">allowed</Badge>
  ) : (
    <Badge variant="outline" className="border-destructive/40 text-destructive">
      denied
    </Badge>
  );
}

function DocList({ title, items }: { title: string; items: React.ReactNode[] }) {
  return (
    <div className="grid gap-1.5">
      <h3 className="text-xs font-medium tracking-wide text-muted-foreground uppercase">{title}</h3>
      {items.length ? <ul className="grid gap-1.5 text-sm">{items}</ul> : <p className="text-sm text-muted-foreground">None</p>}
    </div>
  );
}

function RecordDetail({ record }: { record: MockAuditRecord }) {
  const p = record.payload;
  return (
    <div className="grid gap-5 px-4 pb-6">
      <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm">
        <dt className="text-muted-foreground">Who</dt>
        <dd>
          {p.user_email} ({p.role})
        </dd>
        <dt className="text-muted-foreground">When</dt>
        <dd className="tabular-nums">{formatExact(record.ts)}</dd>
        <dt className="text-muted-foreground">Search</dt>
        <dd>{p.search_mode}</dd>
        <dt className="text-muted-foreground">Live check</dt>
        <dd>{p.live_check_mode}</dd>
        <dt className="text-muted-foreground">LLM</dt>
        <dd>{p.llm_called ? (p.model ?? "called") : "not called"}</dd>
      </dl>
      <DocList title="Question" items={[<li key="q">{p.question}</li>]} />
      <DocList
        title="Candidates and decisions"
        items={p.candidates.map((c) => (
          <li key={c.document} className="flex flex-wrap items-center gap-2">
            <Decision allowed={c.allowed} />
            <code className="text-xs">{c.document}</code>
            <span className="text-xs text-muted-foreground">{c.reason}</span>
          </li>
        ))}
      />
      <DocList
        title="Restricted matches (attempted access)"
        items={p.restricted_matches.map((m) => (
          <li key={m.document} className="flex flex-wrap items-center gap-2">
            <Decision allowed={false} />
            <code className="text-xs">{m.document}</code>
            <span className="text-xs text-muted-foreground">{m.reason}</span>
          </li>
        ))}
      />
      <DocList
        title="Sent to the LLM"
        items={p.sent_to_llm.map((d) => (
          <li key={d}>
            <code className="text-xs">{d}</code>
          </li>
        ))}
      />
      <DocList title="Answer" items={[<li key="a" className="whitespace-pre-wrap">{p.answer}</li>]} />
      <DocList
        title="Hash chain"
        items={[
          <li key="h" className="text-muted-foreground">
            Not built yet (roadmap Task 3, 5–6 Oct).
          </li>,
        ]}
      />
    </div>
  );
}

export function AuditPreview() {
  const [selected, setSelected] = useState<MockAuditRecord | null>(null);
  // Return focus to the row that opened the panel (keyboard users).
  const opener = useRef<HTMLButtonElement | null>(null);
  return (
    <div className="grid gap-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm text-muted-foreground">Chain verification: not built yet.</p>
        <Button variant="outline" size="sm" disabled>
          <ShieldCheck aria-hidden="true" />
          Verify chain
        </Button>
      </div>
      <Filters />
      <div className="overflow-x-auto rounded-lg border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Time</TableHead>
              <TableHead>User</TableHead>
              <TableHead>Question</TableHead>
              <TableHead className="text-right">Sent to LLM</TableHead>
              <TableHead className="text-right">Restricted</TableHead>
              <TableHead className="text-right">Ref</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {MOCK_AUDIT_RECORDS.map((record) => (
              <TableRow key={record.id}>
                <TableCell className="whitespace-nowrap tabular-nums">{formatExact(record.ts)}</TableCell>
                <TableCell>{record.payload.user_email.split("@")[0]}</TableCell>
                <TableCell className="max-w-64">
                  <button
                    type="button"
                    onClick={(event) => {
                      opener.current = event.currentTarget;
                      setSelected(record);
                    }}
                    className="truncate text-left text-primary underline-offset-4 hover:underline"
                  >
                    {record.payload.question}
                  </button>
                </TableCell>
                <TableCell className="text-right tabular-nums">{record.payload.sent_to_llm.length}</TableCell>
                <TableCell className="text-right tabular-nums">{record.payload.restricted_matches.length}</TableCell>
                <TableCell className="text-right tabular-nums">#{record.id}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
      <Sheet open={selected !== null} onOpenChange={(open) => !open && setSelected(null)}>
        <SheetContent
          className="w-full overflow-y-auto sm:max-w-lg"
          onCloseAutoFocus={(event) => {
            event.preventDefault();
            opener.current?.focus();
          }}
        >
          <SheetHeader>
            <SheetTitle>Audit record #{selected?.id} (mock)</SheetTitle>
            <SheetDescription>Fixture data shaped like a real query record.</SheetDescription>
          </SheetHeader>
          {selected ? <RecordDetail record={selected} /> : null}
        </SheetContent>
      </Sheet>
    </div>
  );
}
