import { expect, type APIRequestContext } from "@playwright/test";
import { readFileSync } from "node:fs";
import path from "node:path";

/** Seeding for the digital-twin specs: upstream's OpenAMRobot model and the two real recordings, through the API. */
export const ROOT = path.resolve(__dirname, "../../../..");
export const EXP = path.join(ROOT, "examples/openamr-cmd-timeout");
const MODEL = path.join(EXP, "model");

export async function seedModel(api: APIRequestContext, project: string) {
  const manifest = JSON.parse(readFileSync(path.join(MODEL, "manifest.json"), "utf-8")) as { files: { path: string }[] };
  const form = new FormData();
  form.append("manifest", JSON.stringify(manifest));
  for (const f of manifest.files) form.append("files", new Blob([readFileSync(path.join(MODEL, f.path))]), path.basename(f.path));
  const r = await api.post(`${project}/twin/models`, { multipart: form });
  expect([200, 201], await r.text()).toContain(r.status());
}

export async function seedRecording(api: APIRequestContext, project: string, runId: string, extra: Record<string, string> = {}) {
  const d = path.join(EXP, "recorded", runId);
  const form = new FormData();
  form.append("label", runId);
  form.append("summary", readFileSync(path.join(d, "bag-summary.json"), "utf-8"));
  form.append("identity", readFileSync(path.join(d, "pap-run-identity.json"), "utf-8"));
  for (const [k, v] of Object.entries(extra)) form.append(k, v);
  form.append("file", new Blob([readFileSync(path.join(d, "bag", "bag_0.mcap"))]), `${runId}.mcap`);
  const r = await api.post(`${project}/twin/recordings`, { multipart: form });
  expect([200, 201], await r.text()).toContain(r.status());
  return (await r.json()) as { id: string };
}
