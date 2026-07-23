// Backend client. NEXT_PUBLIC_API_URL points at FastAPI (default localhost:8000).

const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  status: number;
  constructor(status: number, body: string) {
    super(`${status}: ${body}`);
    this.status = status;
  }
}

async function j<T>(res: Response): Promise<T> {
  if (!res.ok) throw new ApiError(res.status, await res.text());
  return res.json();
}

export interface Run {
  id: string;
  filename: string;
  status: string;
  auto_mode: boolean;
  companies_total: number;
  companies_done: number;
  employees_found: number;
  employees_judged: number;
  employees_approved: number;
  employees_revealed: number;
  credits_spent: number;
  error?: string | null;
  created_at: string;
  stats: {
    companies_found: number;
    companies_not_found: number;
    apollo_used: number;
    lusha_used: number;
  };
}

export interface CompanyRow {
  id: string;
  input_name: string;
  domain?: string;
  status: string;
  customer_type?: string;
  size_tier?: string;
  industry?: string;
  org_employees?: number;
  employees_found: number;
  employees_approved: number;
  employees_revealed: number;
  credits_spent: number;
}

export interface EmployeeRow {
  id: string;
  full_name?: string;
  first_name?: string;
  title?: string;
  seniority?: string;
  has_email?: boolean;
  effective_approved: boolean;
  verdict?: {
    verdict: "enrich" | "skip" | "unsure";
    confidence: number;
    matched_designation?: string;
    function_group?: string;
    reasoning: string;
    from_cache: boolean;
  } | null;
  review: { approved: boolean | null };
  reveal: { status: string; email?: string; engine?: string };
}

export interface SearchOptions {
  country?: string;
  city?: string;
  seniorities?: string[];
  titles?: string[];
  keywords?: string;
  headcount_ranges?: string[];
}

export const api = {
  uploadRun: (file: File, autoMode?: boolean, options?: SearchOptions) => {
    const fd = new FormData();
    fd.append("file", file);
    if (autoMode !== undefined) fd.append("auto_mode", String(autoMode));
    if (options?.country) fd.append("country", options.country);
    if (options?.city) fd.append("city", options.city);
    const { country: _c, city: _ci, ...advanced } = options ?? {};
    const hasAdvanced = Object.values(advanced).some((v) =>
      Array.isArray(v) ? v.length > 0 : Boolean(v),
    );
    if (hasAdvanced) fd.append("search_options", JSON.stringify(advanced));
    return fetch(`${BASE}/api/runs`, { method: "POST", body: fd }).then(j<{ run_id: string }>);
  },
  listRuns: () => fetch(`${BASE}/api/runs`).then(j<Run[]>),
  getRun: (id: string) => fetch(`${BASE}/api/runs/${id}`).then(j<Run>),
  stopRun: (id: string) => fetch(`${BASE}/api/runs/${id}/stop`, { method: "POST" }).then(j<Run>),
  deleteRun: (id: string) =>
    fetch(`${BASE}/api/runs/${id}`, { method: "DELETE" }).then(j<{ deleted: boolean }>),
  runEventsUrl: (id: string) => `${BASE}/api/runs/${id}/events`,
  runCompanies: (id: string) =>
    fetch(`${BASE}/api/runs/${id}/companies`).then(j<CompanyRow[]>),
  companyEmployees: (companyId: string) =>
    fetch(`${BASE}/api/companies/${companyId}/employees`).then(j<EmployeeRow[]>),
  overrideEmployee: (id: string, approved: boolean) =>
    fetch(`${BASE}/api/employees/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ approved }),
    }).then(j),
  estimate: (runId: string) =>
    fetch(`${BASE}/api/runs/${runId}/estimate`, { method: "POST" }).then(
      j<{ estimated_credits: number; budget: number; over_budget: boolean; approved_contacts: number }>,
    ),
  reveal: (runId: string, force = false) =>
    fetch(`${BASE}/api/runs/${runId}/reveal?force=${force}`, { method: "POST" }).then(j),
  exportUrl: (runId: string, includeUnrevealed = false) =>
    `${BASE}/api/runs/${runId}/export?include_unrevealed=${includeUnrevealed}`,
  searchResultsUrl: (runId: string) =>
    `${BASE}/api/runs/${runId}/export?search_only=true`,
  getSettings: () => fetch(`${BASE}/api/settings`).then(j<Record<string, unknown>>),
  putSettings: (values: Record<string, unknown>) =>
    fetch(`${BASE}/api/settings`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(values),
    }).then(j),
  listPrompts: () =>
    fetch(`${BASE}/api/prompts`).then(
      j<{ version: number; active: boolean; body: string; created_at: string }[]>,
    ),
  savePrompt: (body: string) =>
    fetch(`${BASE}/api/prompts`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ body, activate: true }),
    }).then(j),
};
