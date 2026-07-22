import { Minus, Plus } from "lucide-react";

export function Stepper({
  value,
  onChange,
  min = 1,
  max = 30,
}: {
  value: number;
  onChange: (v: number) => void;
  min?: number;
  max?: number;
}) {
  return (
    <div className="flex items-center rounded-md border border-border">
      <button
        type="button"
        onClick={() => onChange(Math.max(min, value - 1))}
        className="flex h-9 w-9 items-center justify-center text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground active:scale-[0.97]"
      >
        <Minus className="h-3.5 w-3.5" strokeWidth={2} />
      </button>
      <span className="w-9 text-center text-sm font-medium tabular text-foreground">{value}</span>
      <button
        type="button"
        onClick={() => onChange(Math.min(max, value + 1))}
        className="flex h-9 w-9 items-center justify-center text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground active:scale-[0.97]"
      >
        <Plus className="h-3.5 w-3.5" strokeWidth={2} />
      </button>
    </div>
  );
}
