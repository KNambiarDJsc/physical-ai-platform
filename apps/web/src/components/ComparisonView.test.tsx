import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { ComparisonOut } from "@/lib/api/client";
import fixture from "@/test/comparison.fixture.json";
import { ComparisonView } from "./ComparisonView";

// A real API response, captured from the full evaluation test against the pinned engine (PAP_WRITE_WEB_FIXTURE=1).
const real = fixture as unknown as ComparisonOut;
const clone = (): ComparisonOut => JSON.parse(JSON.stringify(real)) as ComparisonOut;

describe("ComparisonView", () => {
  it("shows reported and verified results separately, with the engine's verdicts and reasons", () => {
    render(<ComparisonView data={real} episodesHref="/x" />);
    const reported = screen.getByRole("heading", { name: "Reported by the robot" }).parentElement!;
    const verified = screen.getByRole("heading", { name: "Independently verified" }).parentElement!;
    expect(within(reported).getByText("Improvement")).toBeInTheDocument();
    expect(within(verified).getByText("Insufficient evidence")).toBeInTheDocument();
    expect(within(verified).getByText(real.verified!.result.reasons[0]!, { exact: false })).toBeInTheDocument();
  });

  it("labels synthetic evidence and shows the engine's warnings", () => {
    render(<ComparisonView data={real} episodesHref="/x" />);
    expect(screen.getByText("SYNTHETIC EVIDENCE")).toBeInTheDocument();
    expect(screen.getAllByRole("alert").length).toBeGreaterThanOrEqual(real.reported.result.warnings.length);
  });

  it("renders whatever the API says: numbers are not hard-coded", () => {
    const data = clone();
    const b = data.verified!.result.b;
    b.failed = 987;
    b.rate = 0.4321;
    b.ci95 = [0.1111, 0.7777];
    render(<ComparisonView data={data} episodesHref="/x" />);
    const verified = screen.getByRole("heading", { name: "Independently verified" }).parentElement!;
    expect(within(verified).getByText("987")).toBeInTheDocument();
    expect(within(verified).getByText("43.2%")).toBeInTheDocument();
    expect(within(verified).getByText("11.1% – 77.8%")).toBeInTheDocument();
  });

  it("says when there is no independent evidence instead of inventing a verified result", () => {
    const data = clone();
    data.verified = null;
    render(<ComparisonView data={data} episodesHref="/x" />);
    expect(screen.getByText(/declares no independent evidence/)).toBeInTheDocument();
  });

  it("shows provenance: engine commit, binary digest and input checksum", () => {
    render(<ComparisonView data={real} episodesHref="/x" />);
    const prov = real.provenance as { engine: { commit: string }; input_sha256: string };
    expect(screen.getByText(new RegExp(prov.engine.commit.slice(0, 10)))).toBeInTheDocument();
    expect(screen.getByText(prov.input_sha256.replace("sha256:", "").slice(0, 12))).toBeInTheDocument();
  });
});
