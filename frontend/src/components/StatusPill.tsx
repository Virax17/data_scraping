import { cn } from "@/lib/utils";

const CONFIG: Record<string, { label: string; className: string }> = {
  queued: { label: "Queued", className: "bg-pending-bg text-pending" },
  resolving: { label: "Resolving", className: "bg-pending-bg text-pending" },
  sweeping: { label: "Sweeping", className: "bg-pending-bg text-pending" },
  judging: { label: "Judging", className: "bg-pending-bg text-pending" },
  awaiting_review: { label: "Awaiting review", className: "bg-accent text-accent-foreground" },
  revealing: { label: "Revealing", className: "bg-pending-bg text-pending" },
  paused: { label: "Paused", className: "bg-accent text-accent-foreground" },
  done: { label: "Done", className: "bg-success-bg text-success" },
  failed: { label: "Failed", className: "bg-destructive-bg text-destructive" },
  stopped: { label: "Stopped", className: "bg-secondary text-secondary-foreground" },
};

export function StatusPill({ status }: { status: string }) {
  const config = CONFIG[status] ?? { label: status, className: "bg-secondary text-secondary-foreground" };
  return (
    <span
      className={cn("inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium", config.className)}
    >
      {config.label}
    </span>
  );
}
