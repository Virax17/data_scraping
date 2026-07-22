import { Bot, UserCheck } from "lucide-react";
import { cn } from "@/lib/utils";

interface ModeSelectorProps {
  autoMode: boolean;
  onChange: (autoMode: boolean) => void;
}

export function ModeSelector({ autoMode, onChange }: ModeSelectorProps) {
  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
      <button
        type="button"
        onClick={() => onChange(true)}
        className={cn(
          "flex flex-col items-start gap-2 rounded-md border p-3.5 text-left transition-colors",
          autoMode ? "border-primary bg-accent" : "border-border hover:border-primary/50",
        )}
      >
        <div className="flex items-center gap-2">
          <Bot className="h-4 w-4 text-primary" strokeWidth={1.75} />
          <span className="text-sm font-medium text-foreground">AI Automatic</span>
        </div>
        <p className="text-xs text-muted-foreground">
          The judge finds and approves contacts on its own, then reveals them automatically as long
          as the run stays within its credit budget. No review step.
        </p>
      </button>

      <button
        type="button"
        onClick={() => onChange(false)}
        className={cn(
          "flex flex-col items-start gap-2 rounded-md border p-3.5 text-left transition-colors",
          !autoMode ? "border-primary bg-accent" : "border-border hover:border-primary/50",
        )}
      >
        <div className="flex items-center gap-2">
          <UserCheck className="h-4 w-4 text-primary" strokeWidth={1.75} />
          <span className="text-sm font-medium text-foreground">Manual Review</span>
        </div>
        <p className="text-xs text-muted-foreground">
          The judge still finds and pre-checks candidates, but nothing is revealed until you review
          the list per company and confirm.
        </p>
      </button>
    </div>
  );
}
