"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Button } from "@/components/ui/button";
import { ModeSelector } from "@/components/ModeSelector";
import { SearchFiltersForm } from "@/components/SearchFiltersForm";
import type { SearchOptions } from "@/lib/api";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

const NUMERIC = [
  "auto_approve_confidence",
  "sweep_cap_per_company",
  "reveal_cap_per_company",
  "run_credit_budget",
  "judge_batch_size",
  "cerebras_judge_batch_size",
  "contact_freshness_days",
];
const BOOLEAN = ["lusha_fallback", "reveal_phone", "verdict_cache"];
const SIZE_TIERS = ["micro", "small", "mid", "large", "enterprise"];

export default function SettingsPanel() {
  const [values, setValues] = useState<Record<string, unknown> | null>(null);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    api.getSettings().then(setValues).catch(console.error);
  }, []);

  if (!values) return <p className="text-sm text-muted-foreground">Loading…</p>;

  function set(key: string, v: unknown) {
    setValues((prev) => ({ ...prev, [key]: v }));
    setSaved(false);
  }

  async function save() {
    const editable: Record<string, unknown> = {};
    for (const k of [
      ...NUMERIC, ...BOOLEAN, "auto_mode", "reveal_cap_by_size_tier",
      "llm_provider", "llm_model", "cerebras_model", "search_defaults",
    ]) {
      if (values && k in values) editable[k] = values[k];
    }
    await api.putSettings(editable);
    setSaved(true);
  }

  const isCerebras = values.llm_provider === "cerebras";
  const revealCapByTier = (values.reveal_cap_by_size_tier as Record<string, number>) ?? {};
  const searchDefaults = (values.search_defaults as SearchOptions) ?? {};

  return (
    <div className="max-w-xl space-y-5 rounded-lg border border-border bg-card p-5">
      <div>
        <Label className="text-xs text-muted-foreground">Default mode for new runs</Label>
        <div className="mt-1.5">
          <ModeSelector autoMode={Boolean(values.auto_mode)} onChange={(v) => set("auto_mode", v)} />
        </div>
      </div>

      <div>
        <Label className="text-xs text-muted-foreground">Judge engine</Label>
        <Select value={String(values.llm_provider ?? "anthropic")} onValueChange={(v) => set("llm_provider", v)}>
          <SelectTrigger className="mt-1.5 max-w-xs">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="cerebras">Cerebras (free tier — local testing)</SelectItem>
            <SelectItem value="anthropic">Anthropic Claude (production quality)</SelectItem>
          </SelectContent>
        </Select>
        {isCerebras && (
          <p className="mt-1.5 text-xs text-pending">
            Free-tier limits: 5 req/min, 8K context — keep the Cerebras batch size small (default 15). Switch to
            Anthropic for real runs.
          </p>
        )}
      </div>

      <div>
        <Label htmlFor="llm-model" className="text-xs text-muted-foreground">
          {isCerebras ? "Cerebras model" : "LLM model"}
        </Label>
        <Input
          id="llm-model"
          type="text"
          value={String((isCerebras ? values.cerebras_model : values.llm_model) ?? "")}
          onChange={(e) => set(isCerebras ? "cerebras_model" : "llm_model", e.target.value)}
          className="mt-1.5 max-w-xs"
        />
      </div>

      {BOOLEAN.map((k) => (
        <div key={k} className="flex items-center justify-between rounded-md border border-border px-3 py-2.5">
          <p className="text-sm font-medium capitalize text-foreground">{k.replaceAll("_", " ")}</p>
          <Switch checked={Boolean(values[k])} onCheckedChange={(v) => set(k, v)} />
        </div>
      ))}

      <div>
        <Label className="text-xs text-muted-foreground">
          Contacts revealed per company, by size tier
        </Label>
        <p className="mt-0.5 text-xs text-muted-foreground">
          Bigger companies get more contacts revealed, smaller ones fewer — this is what actually
          bounds &ldquo;find more valuable people&rdquo; per run.
        </p>
        <div className="mt-2 grid grid-cols-5 gap-2">
          {SIZE_TIERS.map((tier) => (
            <div key={tier}>
              <Label htmlFor={`tier-${tier}`} className="text-xs capitalize text-muted-foreground">
                {tier}
              </Label>
              <Input
                id={`tier-${tier}`}
                type="number"
                min={0}
                value={Number(revealCapByTier[tier] ?? 0)}
                onChange={(e) =>
                  set("reveal_cap_by_size_tier", { ...revealCapByTier, [tier]: Number(e.target.value) })
                }
                className="mt-1.5 tabular"
              />
            </div>
          ))}
        </div>
      </div>

      {NUMERIC.filter((k) => {
        if (k === "judge_batch_size") return !isCerebras;
        if (k === "cerebras_judge_batch_size") return isCerebras;
        return true;
      }).map((k) => (
        <div key={k}>
          <Label htmlFor={k} className="text-xs capitalize text-muted-foreground">
            {k.replaceAll("_", " ")}
          </Label>
          <Input
            id={k}
            type="number"
            step={k === "auto_approve_confidence" ? 0.05 : 1}
            value={Number(values[k] ?? 0)}
            onChange={(e) => set(k, Number(e.target.value))}
            className="mt-1.5 max-w-xs tabular"
          />
        </div>
      ))}

      <div>
        <Label className="text-xs text-muted-foreground">Default search filters (all runs)</Label>
        <p className="mt-0.5 text-xs text-muted-foreground">
          Applied to every new upload unless overridden on the upload form. Region
          (country/city) is set per run, not here.
        </p>
        <div className="mt-2">
          <SearchFiltersForm
            hideRegion
            value={searchDefaults}
            onChange={(v) => set("search_defaults", v)}
          />
        </div>
      </div>

      <div className="flex items-center gap-3">
        <Button onClick={save}>Save settings</Button>
        {saved && <span className="text-sm font-medium text-success">Saved ✓</span>}
      </div>
    </div>
  );
}
