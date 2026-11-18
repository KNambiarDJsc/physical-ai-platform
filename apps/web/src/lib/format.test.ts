import { describe, expect, it } from "vitest";
import { interval, pct, points, shortDigest } from "./format";

describe("format", () => {
  it("renders missing values as a dash, never as zero", () => {
    expect(pct(null)).toBe("—");
    expect(pct(undefined)).toBe("—");
    expect(pct(Number.NaN)).toBe("—");
    expect(interval(null)).toBe("—");
    expect(points(null)).toBe("—");
  });
  it("formats engine numbers without changing them", () => {
    expect(pct(0.125)).toBe("12.5%");
    expect(interval([0.0546, 0.2611])).toBe("5.5% – 26.1%");
    expect(points(-0.125)).toBe("-12.5 pts");
    expect(points(0.0139)).toBe("+1.4 pts");
    expect(points(0)).toBe("±0.0 pts");
  });
  it("shortens digests", () => {
    expect(shortDigest("sha256:d51af06ff90e01b8a672")).toBe("d51af06ff90e");
  });
});
