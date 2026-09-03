export const API_BASE =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type Project = {
  id: string;
  name: string;
  created_at: string;
  updated_at: string;
  document_count: number;
  finding_count: number;
  analysis_status: string | null;
};

export type DocumentInfo = {
  id: string;
  project_id: string;
  type: "DRAWING" | "SPECIFICATION";
  filename: string;
  page_count: number;
  status: string;
};

export type Stage = {
  stage: string;
  status: "PENDING" | "RUNNING" | "DONE" | "FAILED" | "SKIPPED";
  duration?: number | null;
  note?: string | null;
};

export type Analysis = {
  id: string;
  project_id: string;
  status: "ANALYSIS_STARTED" | "ANALYSIS_COMPLETED" | "ANALYSIS_FAILED";
  error?: string | null;
  model?: string | null;
  stages: Stage[];
};

export type EvidenceInfo = {
  document_id: string;
  page: number;
  bbox?: number[] | null;
  snippet?: string | null;
  crop_path?: string | null;
  document_filename?: string | null;
};

export type ValueInfo = {
  value?: number | null;
  unit?: string | null;
  raw?: string | null;
  display?: string | null;
};

export type Finding = {
  id: string;
  project_id: string;
  type: string;
  severity: "HIGH" | "MEDIUM" | "LOW";
  status: "OPEN" | "CONFIRMED" | "FALSE_POSITIVE" | "NEEDS_REVIEW";
  entity: string;
  parameter?: string | null;
  drawing_value?: ValueInfo | null;
  specification_value?: ValueInfo | null;
  drawing_evidence?: EvidenceInfo | null;
  specification_evidence?: EvidenceInfo | null;
  explanation: string;
  confidence: number;
};

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    cache: "no-store",
  });
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = await response.json();
      if (body?.detail) detail = String(body.detail);
    } catch {
      /* keep statusText */
    }
    throw new Error(detail);
  }
  return response.json() as Promise<T>;
}

export const api = {
  listProjects: () => request<Project[]>("/api/projects"),
  createProject: (name: string) =>
    request<Project>("/api/projects", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name }),
    }),
  getProject: (id: string) => request<Project>(`/api/projects/${id}`),
  listDocuments: (projectId: string) =>
    request<DocumentInfo[]>(`/api/projects/${projectId}/documents`),
  uploadDocument: async (
    projectId: string,
    type: "DRAWING" | "SPECIFICATION",
    file: File,
  ) => {
    const form = new FormData();
    form.append("file", file);
    return request<DocumentInfo>(
      `/api/projects/${projectId}/documents?type=${type}`,
      { method: "POST", body: form },
    );
  },
  startAnalysis: (projectId: string) =>
    request<Analysis>(`/api/projects/${projectId}/analyze`, { method: "POST" }),
  getAnalysis: (projectId: string) =>
    request<Analysis>(`/api/projects/${projectId}/analysis`),
  listFindings: (projectId: string, params?: Record<string, string>) => {
    const query = params ? `?${new URLSearchParams(params)}` : "";
    return request<Finding[]>(`/api/projects/${projectId}/findings${query}`);
  },
  getFinding: (id: string) => request<Finding>(`/api/findings/${id}`),
  confirmFinding: (id: string) =>
    request<Finding>(`/api/findings/${id}/confirm`, { method: "POST" }),
  falsePositive: (id: string) =>
    request<Finding>(`/api/findings/${id}/false-positive`, { method: "POST" }),
};

export const evidenceImageUrl = (findingId: string, side: "drawing" | "spec") =>
  `${API_BASE}/api/findings/${findingId}/evidence/${side}.png`;

export const pageImageUrl = (documentId: string, page: number) =>
  `${API_BASE}/api/documents/${documentId}/pages/${page}.png`;
