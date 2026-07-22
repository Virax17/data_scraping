"use client";

import { useCallback, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { FileSpreadsheet, UploadCloud, X } from "lucide-react";
import { TopBar } from "@/components/TopBar";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { ModeSelector } from "@/components/ModeSelector";
import { cn } from "@/lib/utils";
import { api } from "@/lib/api";

export default function UploadPage() {
  const router = useRouter();
  const [file, setFile] = useState<File | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const [autoMode, setAutoMode] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const handleFile = useCallback((f: File | undefined | null) => {
    if (f) setFile(f);
  }, []);

  function onDrop(e: React.DragEvent<HTMLDivElement>) {
    e.preventDefault();
    setDragOver(false);
    handleFile(e.dataTransfer.files?.[0]);
  }

  async function submit() {
    if (!file) return;
    setBusy(true);
    setError(null);
    try {
      const { run_id } = await api.uploadRun(file, autoMode);
      router.push(`/runs/${run_id}`);
    } catch (e) {
      setError(String(e));
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-1 flex-col overflow-hidden">
      <TopBar title="New Enrichment Run" subtitle="Upload a company list to resolve, sweep, and judge contacts" />

      <div className="flex-1 overflow-y-auto p-6">
        <div className="grid grid-cols-1 gap-5 lg:grid-cols-[minmax(0,1fr)_360px]">
          <div className="rounded-lg border border-border bg-card p-5">
            <h2 className="mb-3 text-sm font-medium text-foreground">Upload company list</h2>
            <div
              onDragOver={(e) => {
                e.preventDefault();
                setDragOver(true);
              }}
              onDragLeave={() => setDragOver(false)}
              onDrop={onDrop}
              onClick={() => inputRef.current?.click()}
              className={cn(
                "flex min-h-[220px] cursor-pointer flex-col items-center justify-center gap-3 rounded-md border-2 border-dashed transition-colors",
                dragOver ? "border-primary bg-accent" : "border-border hover:border-primary/50",
              )}
            >
              <input
                ref={inputRef}
                type="file"
                accept=".xlsx,.xls,.csv"
                className="hidden"
                onChange={(e) => handleFile(e.target.files?.[0])}
              />
              {file ? (
                <div className="flex items-center gap-3 rounded-md border border-border bg-background px-4 py-3">
                  <FileSpreadsheet className="h-5 w-5 text-primary" strokeWidth={1.75} />
                  <span className="text-sm font-medium text-foreground">{file.name}</span>
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      setFile(null);
                    }}
                    className="rounded p-0.5 text-muted-foreground hover:text-foreground"
                  >
                    <X className="h-4 w-4" />
                  </button>
                </div>
              ) : (
                <>
                  <UploadCloud className="h-8 w-8 text-muted-foreground" strokeWidth={1.5} />
                  <div className="text-center">
                    <p className="text-sm font-medium text-foreground">Drag a file here, or click to browse</p>
                    <p className="mt-0.5 text-xs text-muted-foreground">
                      .xlsx, .xls, or .csv with company name and website columns
                    </p>
                  </div>
                </>
              )}
            </div>

            {error && <p className="mt-3 rounded-md bg-destructive-bg px-3 py-2 text-sm text-destructive">{error}</p>}
          </div>

          <div className="space-y-4 rounded-lg border border-border bg-card p-5">
            <h2 className="text-sm font-medium text-foreground">Mode</h2>
            <ModeSelector autoMode={autoMode} onChange={setAutoMode} />

            <Label className="block text-xs text-muted-foreground">
              Every other knob (budget caps, sweep size, judge threshold) lives in{" "}
              <span className="font-medium text-foreground">Settings</span> and is snapshotted onto this run.
            </Label>

            <Button className="w-full" disabled={!file || busy} onClick={submit}>
              {busy ? "Uploading…" : "Start run"}
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
