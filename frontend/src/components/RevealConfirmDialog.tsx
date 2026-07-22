"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";

interface Estimate {
  estimated_credits: number;
  budget: number;
  over_budget: boolean;
  approved_contacts: number;
}

export default function RevealConfirmDialog({
  runId,
  onClose,
}: {
  runId: string;
  onClose: () => void;
}) {
  const [est, setEst] = useState<Estimate | null>(null);
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);

  useEffect(() => {
    api.estimate(runId).then(setEst).catch(console.error);
  }, [runId]);

  async function confirm() {
    if (!est) return;
    setBusy(true);
    await api.reveal(runId, est.over_budget);
    setDone(true);
    setBusy(false);
  }

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Confirm reveal (spends credits)</DialogTitle>
        </DialogHeader>

        {!est ? (
          <p className="text-sm text-muted-foreground">Estimating…</p>
        ) : done ? (
          <p className="text-sm text-foreground">Reveal queued — watch the progress above.</p>
        ) : (
          <>
            <p className="text-sm text-foreground">
              <span className="font-medium tabular">{est.approved_contacts}</span> approved contacts &rarr;{" "}
              <span className="font-medium tabular">{est.estimated_credits}</span> estimated credits (budget{" "}
              {est.budget})
            </p>
            {est.over_budget && (
              <p className="rounded-md bg-destructive-bg px-3 py-2 text-sm text-destructive">
                Over budget — confirming will force-proceed anyway.
              </p>
            )}
            <DialogFooter>
              <Button variant="outline" onClick={onClose}>
                Cancel
              </Button>
              <Button onClick={confirm} disabled={busy}>
                {busy ? "Starting…" : est.over_budget ? "Force reveal" : "Reveal now"}
              </Button>
            </DialogFooter>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}
