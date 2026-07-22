"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { TopBar } from "@/components/TopBar";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import SettingsPanel from "@/components/SettingsPanel";

function PromptEditor() {
  const [prompts, setPrompts] = useState<{ version: number; active: boolean; body: string }[]>([]);
  const [draft, setDraft] = useState("");
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    api.listPrompts().then((ps) => {
      setPrompts(ps);
      const active = ps.find((p) => p.active);
      if (active) setDraft(active.body);
    });
  }, []);

  async function savePrompt() {
    await api.savePrompt(draft);
    setSaved(true);
    api.listPrompts().then(setPrompts);
  }

  return (
    <div className="rounded-lg border border-border bg-card p-5">
      <p className="mb-3 text-sm text-muted-foreground">
        This prompt IS the filtering logic — who gets enriched is decided here, not in code. Saving creates a
        new version and activates it; old versions stay for audit ({prompts.length} versions so far).
      </p>
      <textarea
        rows={24}
        value={draft}
        onChange={(e) => {
          setDraft(e.target.value);
          setSaved(false);
        }}
        className="w-full rounded-md border border-input bg-transparent p-3 font-mono text-xs text-foreground shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
      />
      <div className="mt-3 flex items-center gap-3">
        <Button onClick={savePrompt}>Save as new version + activate</Button>
        {saved && <span className="text-sm font-medium text-success">Saved ✓</span>}
      </div>
    </div>
  );
}

export default function SettingsPage() {
  return (
    <div className="flex flex-1 flex-col overflow-hidden">
      <TopBar title="Settings" subtitle="Pipeline defaults and the judge system prompt" />
      <div className="flex-1 overflow-y-auto p-6">
        <Tabs defaultValue="general">
          <TabsList>
            <TabsTrigger value="general">General</TabsTrigger>
            <TabsTrigger value="prompt">Judge prompt</TabsTrigger>
          </TabsList>
          <TabsContent value="general" className="mt-5">
            <SettingsPanel />
          </TabsContent>
          <TabsContent value="prompt" className="mt-5">
            <PromptEditor />
          </TabsContent>
        </Tabs>
      </div>
    </div>
  );
}
