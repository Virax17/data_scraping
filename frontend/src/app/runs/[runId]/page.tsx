"use client";

import { Fragment, use, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Download, Search, ShieldCheck, Square, Trash2 } from "lucide-react";
import { api, ApiError, type CompanyRow, type Run } from "@/lib/api";
import { TopBar } from "@/components/TopBar";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import RunProgress from "@/components/RunProgress";
import EmployeeReviewTable from "@/components/EmployeeReviewTable";
import RevealConfirmDialog from "@/components/RevealConfirmDialog";

const STOPPABLE_STATUSES = new Set([
  "queued", "resolving", "sweeping", "judging", "awaiting_review", "revealing",
]);

export default function RunDetailPage({ params }: { params: Promise<{ runId: string }> }) {
  const { runId } = use(params);
  const router = useRouter();
  const [run, setRun] = useState<Run | null>(null);
  const [notFound, setNotFound] = useState(false);
  const [companies, setCompanies] = useState<CompanyRow[]>([]);
  const [openCompany, setOpenCompany] = useState<string | null>(null);
  const [showReveal, setShowReveal] = useState(false);
  const [includeUnrevealed, setIncludeUnrevealed] = useState(false);
  const [busy, setBusy] = useState(false);

  async function handleStop() {
    if (!run || !confirm("Stop this run? In-progress companies will finish their current step, then halt.")) return;
    setBusy(true);
    try {
      setRun(await api.stopRun(run.id));
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) {
        router.push("/runs");
      } else {
        console.error(err);
      }
    } finally {
      setBusy(false);
    }
  }

  async function handleDelete() {
    if (!run || !confirm(`Delete "${run.filename}" and all its data? This cannot be undone.`)) return;
    try {
      await api.deleteRun(run.id);
    } catch (err) {
      if (!(err instanceof ApiError && err.status === 404)) {
        console.error(err);
        return;
      }
    }
    router.push("/runs");
  }

  useEffect(() => {
    api
      .getRun(runId)
      .then(setRun)
      .catch((err) => {
        if (err instanceof ApiError && err.status === 404) {
          setNotFound(true);
        } else {
          console.error(err);
        }
      });
    if (notFound) return;
    const es = new EventSource(api.runEventsUrl(runId));
    es.onmessage = (e) => setRun(JSON.parse(e.data));
    es.onerror = () => es.close();
    return () => es.close();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [runId, notFound]);

  useEffect(() => {
    if (notFound) return;
    api.runCompanies(runId).then(setCompanies).catch(console.error);
    const t = setInterval(() => api.runCompanies(runId).then(setCompanies).catch(() => {}), 5000);
    return () => clearInterval(t);
  }, [runId, notFound]);

  if (notFound) {
    return (
      <div className="flex flex-1 flex-col overflow-hidden">
        <TopBar title="Run" />
        <div className="flex-1 p-6 text-sm text-muted-foreground">
          This run could not be found — it may have been deleted.{" "}
          <a href="/runs" className="text-primary underline">
            Back to dashboard
          </a>
        </div>
      </div>
    );
  }

  if (!run) {
    return (
      <div className="flex flex-1 flex-col overflow-hidden">
        <TopBar title="Run" />
        <div className="flex-1 p-6 text-sm text-muted-foreground">Loading…</div>
      </div>
    );
  }

  return (
    <div className="flex flex-1 flex-col overflow-hidden">
      <TopBar
        title={run.filename}
        subtitle={`Run ${run.id}`}
        actions={
          <>
            <label className="flex items-center gap-1.5 text-xs text-muted-foreground">
              <Checkbox
                checked={includeUnrevealed}
                onCheckedChange={(v) => setIncludeUnrevealed(Boolean(v))}
              />
              Include approved-but-unrevealed
            </label>
            <Button variant="outline" className="gap-1.5" onClick={() => setShowReveal(true)}>
              <ShieldCheck className="h-4 w-4" strokeWidth={2} />
              Reveal approved…
            </Button>
            {STOPPABLE_STATUSES.has(run.status) && (
              <Button variant="outline" className="gap-1.5" disabled={busy} onClick={handleStop}>
                <Square className="h-4 w-4" strokeWidth={2} />
                Stop
              </Button>
            )}
            <Button
              variant="outline"
              className="gap-1.5 text-destructive hover:text-destructive"
              onClick={handleDelete}
            >
              <Trash2 className="h-4 w-4" strokeWidth={2} />
              Delete
            </Button>
            <a href={api.searchResultsUrl(run.id)}>
              <Button variant="outline" className="gap-1.5">
                <Search className="h-4 w-4" strokeWidth={2} />
                Search results only (free)
              </Button>
            </a>
            <a href={api.exportUrl(run.id, includeUnrevealed)}>
              <Button className="gap-1.5">
                <Download className="h-4 w-4" strokeWidth={2} />
                Download Excel
              </Button>
            </a>
          </>
        }
      />

      <div className="flex-1 overflow-y-auto p-6">
        <RunProgress run={run} />

        {run.error && (
          <p className="mt-4 rounded-md bg-destructive-bg px-3 py-2 text-sm text-destructive">{run.error}</p>
        )}

        {showReveal && <RevealConfirmDialog runId={run.id} onClose={() => setShowReveal(false)} />}

        <div className="mt-6 rounded-lg border border-border bg-card">
          <div className="border-b border-border px-4 py-3">
            <h2 className="text-sm font-medium text-foreground">Companies</h2>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border text-left text-xs text-muted-foreground">
                  <th className="px-4 py-2.5 font-medium">Company</th>
                  <th className="px-4 py-2.5 font-medium">Status</th>
                  <th className="px-4 py-2.5 font-medium">Type</th>
                  <th className="px-4 py-2.5 font-medium">Tier</th>
                  <th className="px-4 py-2.5 font-medium text-right">Found</th>
                  <th className="px-4 py-2.5 font-medium text-right">Approved</th>
                  <th className="px-4 py-2.5 font-medium text-right">Revealed</th>
                  <th className="px-4 py-2.5 font-medium"></th>
                </tr>
              </thead>
              <tbody>
                {companies.map((c) => (
                  <Fragment key={c.id}>
                    <tr
                      className="h-12 cursor-pointer border-b border-border last:border-0 hover:bg-secondary/60"
                      onClick={() => setOpenCompany(openCompany === c.id ? null : c.id)}
                    >
                      <td className="px-4 font-medium text-foreground">{c.input_name}</td>
                      <td className="px-4 text-foreground">{c.status}</td>
                      <td className="px-4 text-foreground">{c.customer_type ?? "—"}</td>
                      <td className="px-4 text-foreground">{c.size_tier ?? "—"}</td>
                      <td className="px-4 text-right tabular text-foreground">{c.employees_found}</td>
                      <td className="px-4 text-right tabular text-foreground">{c.employees_approved}</td>
                      <td className="px-4 text-right tabular text-foreground">{c.employees_revealed}</td>
                      <td className="px-4 text-right text-xs font-medium text-primary">
                        {openCompany === c.id ? "Hide" : "Review"}
                      </td>
                    </tr>
                    {openCompany === c.id && (
                      <tr>
                        <td colSpan={8} className="bg-secondary/20 px-4 py-3">
                          <EmployeeReviewTable companyId={c.id} />
                        </td>
                      </tr>
                    )}
                  </Fragment>
                ))}
                {companies.length === 0 && (
                  <tr>
                    <td colSpan={8} className="px-4 py-10 text-center text-sm text-muted-foreground">
                      No companies yet — the run is still starting up.
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
