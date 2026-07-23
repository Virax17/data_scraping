"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Plus, Trash2 } from "lucide-react";
import { TopBar } from "@/components/TopBar";
import { StatCard } from "@/components/StatCard";
import { StatusPill } from "@/components/StatusPill";
import { Button } from "@/components/ui/button";
import { api, type Run } from "@/lib/api";

export default function RunsPage() {
  const router = useRouter();
  const [runs, setRuns] = useState<Run[]>([]);

  useEffect(() => {
    api.listRuns().then(setRuns).catch(console.error);
  }, []);

  const activeRuns = runs.filter((r) => r.status !== "done" && r.status !== "failed").length;
  const totalRevealed = runs.reduce((sum, r) => sum + r.employees_revealed, 0);
  const totalCredits = runs.reduce((sum, r) => sum + r.credits_spent, 0);

  async function handleDelete(e: React.MouseEvent, run: Run) {
    e.stopPropagation();
    if (!confirm(`Delete "${run.filename}" and all its data? This cannot be undone.`)) return;
    await api.deleteRun(run.id);
    setRuns((prev) => prev.filter((r) => r.id !== run.id));
  }

  return (
    <div className="flex flex-1 flex-col overflow-hidden">
      <TopBar
        title="Dashboard"
        subtitle="Overview of enrichment activity across all runs"
        actions={
          <Button onClick={() => router.push("/upload")} className="gap-1.5">
            <Plus className="h-4 w-4" strokeWidth={2} />
            New enrichment
          </Button>
        }
      />

      <div className="flex-1 overflow-y-auto p-6">
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <StatCard label="Total runs" value={String(runs.length)} />
          <StatCard label="Active runs" value={String(activeRuns)} />
          <StatCard label="Contacts revealed" value={String(totalRevealed)} />
          <StatCard label="Credits spent" value={String(totalCredits)} />
        </div>

        <div className="mt-6 rounded-lg border border-border bg-card">
          <div className="border-b border-border px-4 py-3">
            <h2 className="text-sm font-medium text-foreground">Runs</h2>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border text-left text-xs text-muted-foreground">
                  <th className="px-4 py-2.5 font-medium">Source file</th>
                  <th className="px-4 py-2.5 font-medium text-right">Companies</th>
                  <th className="px-4 py-2.5 font-medium text-right">Found</th>
                  <th className="px-4 py-2.5 font-medium text-right">Approved</th>
                  <th className="px-4 py-2.5 font-medium text-right">Revealed</th>
                  <th className="px-4 py-2.5 font-medium text-right">Credits</th>
                  <th className="px-4 py-2.5 font-medium">Started</th>
                  <th className="px-4 py-2.5 font-medium">Status</th>
                  <th className="px-4 py-2.5 font-medium"></th>
                </tr>
              </thead>
              <tbody>
                {runs.map((r) => (
                  <tr
                    key={r.id}
                    onClick={() => router.push(`/runs/${r.id}`)}
                    className="h-12 cursor-pointer border-b border-border last:border-0 hover:bg-secondary/60"
                  >
                    <td className="px-4 font-medium text-foreground">{r.filename}</td>
                    <td className="px-4 text-right tabular text-foreground">
                      {r.companies_done}/{r.companies_total}
                    </td>
                    <td className="px-4 text-right tabular text-foreground">{r.employees_found}</td>
                    <td className="px-4 text-right tabular text-foreground">{r.employees_approved}</td>
                    <td className="px-4 text-right tabular text-foreground">{r.employees_revealed}</td>
                    <td className="px-4 text-right tabular text-foreground">{r.credits_spent}</td>
                    <td className="px-4 tabular text-foreground">{new Date(r.created_at).toLocaleString()}</td>
                    <td className="px-4">
                      <StatusPill status={r.status} />
                    </td>
                    <td className="px-4 text-right">
                      <button
                        onClick={(e) => handleDelete(e, r)}
                        className="rounded p-1.5 text-muted-foreground hover:bg-destructive-bg hover:text-destructive"
                        title="Delete run"
                      >
                        <Trash2 className="h-4 w-4" strokeWidth={2} />
                      </button>
                    </td>
                  </tr>
                ))}
                {runs.length === 0 && (
                  <tr>
                    <td colSpan={9} className="px-4 py-10 text-center text-sm text-muted-foreground">
                      No runs yet. Start one from &ldquo;New enrichment&rdquo;.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}
