import type {
  Connectors,
  GenerateBatchInput,
  GenerateBatchResult,
  ImportCommitResult,
  ImportFormat,
  ImportPreview,
  ScriptCandidate,
  StoryboardShot,
  Video,
  Workspace,
} from "./domain";

interface ApiErrorBody {
  code?: string;
  message?: string;
  detail?: string | { message?: string };
  error?: {
    code?: string;
    message?: string;
  };
}

export class ApiError extends Error {
  constructor(
    message: string,
    readonly code = "request_failed",
    readonly status = 500,
  ) {
    super(message);
  }
}

/** 原样返回响应体，不剥 {data: …} 信封——connectors 自己就有顶层 "data" 段，剥了会剥错 */
async function requestRaw<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, init);
  const body = (await response.json().catch(() => null)) as ApiErrorBody | T | null;
  if (!response.ok) {
    const error = (body ?? {}) as ApiErrorBody;
    const detail = typeof error.detail === "string" ? error.detail : error.detail?.message;
    const message = error.error?.message ?? error.message ?? detail ?? "操作失败，请稍后重试。";
    const code = error.error?.code ?? error.code;
    throw new ApiError(message, code, response.status);
  }
  return body as T;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const body = await requestRaw<T | { data: T }>(path, init);
  if (body && typeof body === "object" && "data" in body) return (body as { data: T }).data;
  return body as T;
}

function json(method: string, body: unknown): RequestInit {
  return { method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) };
}

export const api = {
  workspace: () => request<Workspace>("/api/workspace"),
  fetchConnectors: () => requestRaw<Connectors>("/api/connectors"),
  createGroup: (body: Record<string, unknown>) => request("/api/account-groups", json("POST", body)),
  createAccount: (body: Record<string, unknown>) => request("/api/accounts", json("POST", body)),
  inspectAccount: (id: string) => request(`/api/accounts/${id}/inspect`, json("POST", {})),
  createProduct: (body: Record<string, unknown>) => request("/api/products", json("POST", body)),
  createVideo: (body: Record<string, unknown>) => request<Video>("/api/videos", json("POST", body)),
  updateVideoTitle: (id: string, title: string) =>
    request<Video>(`/api/videos/${id}`, json("PATCH", { title })),
  generateBatch: (body: GenerateBatchInput) =>
    request<GenerateBatchResult>("/api/batches/generate", json("POST", body)),
  updateCandidate: (
    batchId: string,
    candidateId: string,
    body: { title?: string; script: string; shots: StoryboardShot[] },
  ) => request<ScriptCandidate>(`/api/batches/${batchId}/candidates/${candidateId}`, json("PATCH", body)),
  regenerateCandidate: (batchId: string, candidateId: string, producer: string) =>
    request<ScriptCandidate>(`/api/batches/${batchId}/candidates/${candidateId}/regenerate`, json("POST", { producer })),
  selectCandidates: (batchId: string, candidateIds: string[]) =>
    request<{ videos: Video[] }>(`/api/batches/${batchId}/select`, json("POST", { candidate_ids: candidateIds })),
  generate: (id: string, instruction: string, producer = "mock") =>
    request(`/api/videos/${id}/generate`, json("POST", { instruction, producer })),
  importArtifacts: (id: string, script: string, shots?: StoryboardShot[]) =>
    request(`/api/videos/${id}/import`, json("POST", { script, shots })),
  updateScript: (id: string, content: string, note: string, shots?: StoryboardShot[]) =>
    request(`/api/videos/${id}/script`, json("POST", { content, note, shots })),
  uploadMedia: (id: string, file: File) => {
    const body = new FormData();
    body.append("file", file);
    return request(`/api/videos/${id}/media`, { method: "POST", body });
  },
  arrange: (id: string, accountIds: string[], scheduledAt: string | null) =>
    request(`/api/videos/${id}/publications`, json("POST", { account_ids: accountIds, scheduled_at: scheduledAt })),
  execute: (id: string, confirmed: boolean) =>
    request(`/api/publications/${id}/execute`, json("POST", { confirmed })),
  reconcile: (id: string, body: Record<string, unknown>) =>
    request(`/api/publications/${id}/reconcile`, json("POST", body)),
  confirmAbsent: (id: string, note: string) =>
    request(`/api/publications/${id}/confirm-absent`, json("POST", { confirmed_absent: true, note })),
  sync: (id: string) => request(`/api/publications/${id}/sync`, json("POST", {})),
  importPublication: (id: string, body: Record<string, unknown>) =>
    request(`/api/videos/${id}/publications/import`, json("POST", body)),
  branch: (id: string, variation: string, commentIds: string[]) =>
    request(`/api/videos/${id}/branch`, json("POST", { variation, comment_ids: commentIds })),
  batch: (id: string, name: string, variations: string[]) =>
    request(`/api/videos/${id}/batch`, json("POST", { name, variations })),
  previewImport: (format: ImportFormat, payload: string) =>
    request<ImportPreview>("/api/import/preview", json("POST", { format, payload })),
  commitImport: (format: ImportFormat, payload: string) =>
    request<ImportCommitResult>("/api/import/commit", json("POST", { format, payload })),
};
