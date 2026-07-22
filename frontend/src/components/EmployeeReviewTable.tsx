"use client";

import { useEffect, useState } from "react";
import { api, type EmployeeRow } from "@/lib/api";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { cn } from "@/lib/utils";

const VERDICT_STYLE: Record<string, string> = {
  enrich: "bg-success-bg text-success",
  skip: "bg-destructive-bg text-destructive",
  unsure: "bg-accent text-accent-foreground",
};

export default function EmployeeReviewTable({ companyId }: { companyId: string }) {
  const [rows, setRows] = useState<EmployeeRow[]>([]);
  const [filter, setFilter] = useState<string>("all");

  const load = () => api.companyEmployees(companyId).then(setRows).catch(console.error);
  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [companyId]);

  async function toggle(row: EmployeeRow) {
    await api.overrideEmployee(row.id, !row.effective_approved);
    load();
  }

  const visible = rows.filter((r) => (filter === "all" ? true : r.verdict?.verdict === filter));

  return (
    <div className="rounded-md border border-border bg-secondary/30 p-3">
      <div className="mb-2 flex items-center gap-3">
        <Select value={filter} onValueChange={setFilter}>
          <SelectTrigger className="h-8 w-40 text-xs">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All</SelectItem>
            <SelectItem value="enrich">Enrich</SelectItem>
            <SelectItem value="unsure">Unsure</SelectItem>
            <SelectItem value="skip">Skip</SelectItem>
          </SelectContent>
        </Select>
        <span className="text-xs text-muted-foreground">
          {rows.length} people — checkbox controls who gets revealed
        </span>
      </div>
      <div className="overflow-x-auto rounded-md border border-border bg-card">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border text-left text-xs text-muted-foreground">
              <th className="w-10 px-3 py-2"></th>
              <th className="px-3 py-2 font-medium">Name</th>
              <th className="px-3 py-2 font-medium">Title</th>
              <th className="px-3 py-2 font-medium">Verdict</th>
              <th className="px-3 py-2 font-medium">Confidence</th>
              <th className="px-3 py-2 font-medium">Reasoning</th>
              <th className="px-3 py-2 font-medium">Email</th>
            </tr>
          </thead>
          <tbody>
            {visible.map((r) => (
              <tr key={r.id} className="border-b border-border last:border-0">
                <td className="px-3 py-2">
                  <Checkbox
                    checked={r.effective_approved}
                    disabled={["revealed", "cached"].includes(r.reveal.status)}
                    onCheckedChange={() => toggle(r)}
                  />
                </td>
                <td className="px-3 py-2 font-medium text-foreground">
                  {r.full_name ?? r.first_name ?? "—"}
                </td>
                <td className="px-3 py-2 text-foreground">{r.title ?? "—"}</td>
                <td className="px-3 py-2">
                  {r.verdict ? (
                    <span
                      className={cn(
                        "inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium",
                        VERDICT_STYLE[r.verdict.verdict],
                      )}
                    >
                      {r.verdict.verdict}
                      {r.verdict.from_cache ? " ⚡" : ""}
                    </span>
                  ) : (
                    "—"
                  )}
                </td>
                <td className="px-3 py-2">
                  {r.verdict && (
                    <span
                      className="inline-block h-1.5 w-16 overflow-hidden rounded-full bg-secondary align-middle"
                      title={r.verdict.confidence.toFixed(2)}
                    >
                      <span
                        className="block h-full bg-success"
                        style={{ width: `${r.verdict.confidence * 100}%` }}
                      />
                    </span>
                  )}
                </td>
                <td className="max-w-[280px] px-3 py-2 text-xs text-muted-foreground">
                  {r.verdict?.reasoning ?? ""}
                </td>
                <td className="px-3 py-2 text-foreground">
                  {r.reveal.email ?? (r.reveal.status === "failed" ? "✗" : "")}
                </td>
              </tr>
            ))}
            {visible.length === 0 && (
              <tr>
                <td colSpan={7} className="px-3 py-6 text-center text-xs text-muted-foreground">
                  No employees match this filter.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
