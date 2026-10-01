import { keycloak } from "./keycloak";

const BASE_URL = import.meta.env.VITE_API_URL;

export class ApiError extends Error {
  status: number;
  detail: string;

  constructor(status: number, detail: string) {
    super(detail);
    this.status = status;
    this.detail = detail;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  await keycloak.updateToken(30).catch(() => keycloak.login());
  const res = await fetch(`${BASE_URL}${path}`, {
    ...init,
    headers: {
      ...(init?.body ? { "Content-Type": "application/json" } : {}),
      Authorization: `Bearer ${keycloak.token}`,
      ...init?.headers,
    },
  });
  if (!res.ok) {
    // RFC 7807 problem+json (api/api/app.py's _problem()).
    const problem = await res.json().catch(() => ({ detail: res.statusText }));
    const detail = typeof problem.detail === "string" ? problem.detail : JSON.stringify(problem.detail);
    throw new ApiError(res.status, detail || problem.title || "request failed");
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: "POST", body: body ? JSON.stringify(body) : undefined }),
};

export function wsUrl(path: string): string {
  const httpBase = new URL(BASE_URL);
  const scheme = httpBase.protocol === "https:" ? "wss:" : "ws:";
  return `${scheme}//${httpBase.host}${path}?token=${encodeURIComponent(keycloak.token ?? "")}`;
}
