import { StatCard } from "@/components/StatCard";
import { StatusPill } from "@/components/StatusPill";
import type { Run } from "@/lib/api";

export default function RunProgress({ run }: { run: Run }) {
  return (
    <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-6">
      <div className="rounded-lg border border-border bg-card p-4">
        <p className="text-sm text-muted-foreground">Status</p>
        <div className="mt-1.5">
          <StatusPill status={run.status} />
        </div>
      </div>
      <StatCard label="Companies" value={`${run.companies_done}/${run.companies_total}`} />
      <StatCard label="Employees found" value={String(run.employees_found)} />
      <StatCard label="Judged" value={String(run.employees_judged)} />
      <StatCard label="Approved" value={String(run.employees_approved)} />
      <StatCard label="Revealed" value={String(run.employees_revealed)} />
    </div>
  );
}
