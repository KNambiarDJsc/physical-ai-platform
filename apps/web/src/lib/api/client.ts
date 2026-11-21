import type { components } from "./schema";
import { getIdentity } from "../identity";

export type Schemas = components["schemas"];
export type Evaluation = Schemas["EvaluationOut"];
export type ComparisonOut = Schemas["ComparisonOut"];
export type Comparison = Schemas["Comparison"];
export type Arm = Schemas["Arm"];
export type Release = Schemas["ReleaseOut"];
export type Artifact = Schemas["ArtifactOut"];
export type Mapping = Schemas["MappingOut"];
export type Project = Schemas["ProjectOut"];
export type EpisodePage = Schemas["EpisodePage"];
export type EpisodeDetail = Schemas["EpisodeDetail"];
export type CatalogEntry = Schemas["CatalogEntryOut"];
export type Environment = Schemas["EnvironmentOut"];
export type Device = Schemas["DeviceOut"];
export type DeviceDetail = Schemas["DeviceDetailOut"];
export type Capability = Schemas["CapabilityOut"];
export type Discovery = Schemas["DiscoveryOut"];
export type PropertyRead = Schemas["PropertyReadOut"];
export type WorkflowTemplate = Schemas["TemplateOut"];
export type Workflow = Schemas["WorkflowOut"];
export type WorkflowRun = Schemas["RunOut"];
export type WorkflowRunDetail = Schemas["RunDetailOut"];
export type WorkflowStep = Schemas["StepOut"];
export const orgPath = (org: string) => `/api/v1/orgs/${org}`;

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
  ) {
    super(message);
  }
}

/** Calls the API through the web origin (proxied by next.config rewrites). */
export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  const identity = getIdentity();
  if (identity) headers.set("Authorization", `Bearer ${identity}`);
  if (init.body && !(init.body instanceof FormData)) headers.set("Content-Type", "application/json");
  const res = await fetch(path, { ...init, headers, cache: "no-store" });
  if (!res.ok) {
    let code = "http_error";
    let message = `${res.status} ${res.statusText}`;
    try {
      const body = (await res.json()) as { detail?: { code?: string; message?: string } | unknown };
      const d = body.detail as { code?: string; message?: string } | undefined;
      if (d && typeof d === "object" && "code" in d) {
        code = d.code ?? code;
        message = d.message ?? message;
      } else if (body.detail) {
        message = JSON.stringify(body.detail).slice(0, 300);
      }
    } catch {
      /* not JSON */
    }
    throw new ApiError(res.status, code, message);
  }
  return (res.status === 204 ? undefined : await res.json()) as T;
}

export const projectPath = (org: string, project: string) => `/api/v1/orgs/${org}/projects/${project}`;

/** Fetches a file from the API with the caller's identity and hands it to the browser as a download. */
export async function download(path: string, filename: string): Promise<void> {
  const headers = new Headers();
  const identity = getIdentity();
  if (identity) headers.set("Authorization", `Bearer ${identity}`);
  const res = await fetch(path, { headers, cache: "no-store" });
  if (!res.ok) throw new ApiError(res.status, "http_error", `${res.status} ${res.statusText}`);
  const url = URL.createObjectURL(await res.blob());
  try {
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
  } finally {
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
}
