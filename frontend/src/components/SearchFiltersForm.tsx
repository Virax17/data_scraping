"use client";

import { useState } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { cn } from "@/lib/utils";
import type { SearchOptions } from "@/lib/api";
import { CITIES_BY_COUNTRY, COUNTRIES, OTHER_CITY } from "@/lib/locations";

const SENIORITIES = ["owner", "founder", "c_suite", "partner", "vp", "head",
  "director", "manager", "senior", "entry"];

interface SearchFiltersFormProps {
  value: SearchOptions;
  onChange: (value: SearchOptions) => void;
  /** Hide the country/city inputs — used in Settings, where filters are
   * global defaults and region is a per-run/per-company thing set at upload. */
  hideRegion?: boolean;
}

function toCsv(list?: string[]) {
  return (list ?? []).join(", ");
}

function fromCsv(text: string): string[] {
  return text
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
}

// Headcount ranges use Apollo's "min,max" format internally but that reads
// oddly as a comma list in one text box — accept "1-50, 51-200" instead and
// convert dashes to the commas Apollo expects.
function toRangeText(ranges?: string[]) {
  return (ranges ?? []).map((r) => r.replace(",", "-")).join(", ");
}

function fromRangeText(text: string): string[] {
  return text
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean)
    .map((s) => s.replace(/\s*-\s*/, ","));
}

export function SearchFiltersForm({ value, onChange, hideRegion }: SearchFiltersFormProps) {
  const [open, setOpen] = useState(Boolean(hideRegion));
  const cityOptions = value.country ? CITIES_BY_COUNTRY[value.country] ?? [] : [];
  const [cityCustom, setCityCustom] = useState(
    () => Boolean(value.city) && !cityOptions.includes(value.city ?? ""),
  );

  function set<K extends keyof SearchOptions>(key: K, v: SearchOptions[K]) {
    onChange({ ...value, [key]: v });
  }

  function setCountry(country: string) {
    onChange({ ...value, country, city: "" });
    setCityCustom(false);
  }

  function setCity(city: string) {
    if (city === OTHER_CITY) {
      setCityCustom(true);
      set("city", "");
      return;
    }
    set("city", city);
  }

  function toggleSeniority(s: string) {
    const current = value.seniorities ?? [];
    set(
      "seniorities",
      current.includes(s) ? current.filter((x) => x !== s) : [...current, s],
    );
  }

  return (
    <div className="space-y-3">
      {!hideRegion && (
        <>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1">
              <Label className="text-xs text-muted-foreground">Country</Label>
              <Select value={value.country ?? ""} onValueChange={setCountry}>
                <SelectTrigger>
                  <SelectValue placeholder="Any country" />
                </SelectTrigger>
                <SelectContent>
                  {COUNTRIES.map((c) => (
                    <SelectItem key={c} value={c}>
                      {c}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1">
              <Label className="text-xs text-muted-foreground">City</Label>
              {cityOptions.length > 0 && !cityCustom ? (
                <Select value={value.city ?? ""} onValueChange={setCity}>
                  <SelectTrigger>
                    <SelectValue placeholder="Any city" />
                  </SelectTrigger>
                  <SelectContent>
                    {cityOptions.map((c) => (
                      <SelectItem key={c} value={c}>
                        {c}
                      </SelectItem>
                    ))}
                    <SelectItem value={OTHER_CITY}>Other (type manually)…</SelectItem>
                  </SelectContent>
                </Select>
              ) : (
                <Input
                  placeholder={value.country ? "Type a city" : "Pick a country first"}
                  disabled={!value.country}
                  value={value.city ?? ""}
                  onChange={(e) => set("city", e.target.value)}
                />
              )}
            </div>
          </div>
          <p className="text-xs text-muted-foreground">
            Only people (and offices) in this region are swept and enriched. Leave blank to
            search everywhere, as before. A country/city column in your file overrides this
            per company.
          </p>
        </>
      )}

      {!hideRegion && (
        <button
          type="button"
          onClick={() => setOpen((o) => !o)}
          className="flex items-center gap-1 text-xs font-medium text-foreground hover:text-primary"
        >
          {open ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
          Advanced search filters
        </button>
      )}

      {open && (
        <div className={cn("space-y-4 rounded-md border border-border p-3")}>
          <div className="space-y-1.5">
            <Label className="text-xs text-muted-foreground">Seniority levels</Label>
            <div className="flex flex-wrap gap-1.5">
              {SENIORITIES.map((s) => {
                const active = (value.seniorities ?? []).includes(s);
                return (
                  <button
                    key={s}
                    type="button"
                    onClick={() => toggleSeniority(s)}
                    className={cn(
                      "rounded-full border px-2.5 py-1 text-xs transition-colors",
                      active
                        ? "border-primary bg-accent text-foreground"
                        : "border-border text-muted-foreground hover:border-primary/50",
                    )}
                  >
                    {s.replaceAll("_", " ")}
                  </button>
                );
              })}
            </div>
            <p className="text-xs text-muted-foreground">
              None selected = every seniority (default).
            </p>
          </div>

          <div className="space-y-1">
            <Label className="text-xs text-muted-foreground">Job titles (comma-separated)</Label>
            <Input
              placeholder="e.g. Maintenance Manager, Plant Engineer"
              value={toCsv(value.titles)}
              onChange={(e) => set("titles", fromCsv(e.target.value))}
            />
          </div>

          <div className="space-y-1">
            <Label className="text-xs text-muted-foreground">Keywords</Label>
            <Input
              placeholder="e.g. rotating equipment"
              value={value.keywords ?? ""}
              onChange={(e) => set("keywords", e.target.value)}
            />
          </div>

          <div className="space-y-1">
            <Label className="text-xs text-muted-foreground">
              Company headcount ranges
            </Label>
            <Input
              placeholder="e.g. 1-50, 51-200"
              value={toRangeText(value.headcount_ranges)}
              onChange={(e) => set("headcount_ranges", fromRangeText(e.target.value))}
            />
          </div>
        </div>
      )}
    </div>
  );
}
