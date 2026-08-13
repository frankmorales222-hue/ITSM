import { describe, it, expect } from "vitest";
import { calculatePriority, bumpPriority } from "./priority";

describe("calculatePriority", () => {
  it("high impact + high urgency is critical", () => {
    expect(calculatePriority("high", "high")).toBe("critical");
  });

  it("low impact + low urgency is low", () => {
    expect(calculatePriority("low", "low")).toBe("low");
  });

  it("matches the full matrix from the source spec", () => {
    expect(calculatePriority("high", "medium")).toBe("high");
    expect(calculatePriority("high", "low")).toBe("medium");
    expect(calculatePriority("medium", "high")).toBe("high");
    expect(calculatePriority("medium", "medium")).toBe("medium");
    expect(calculatePriority("medium", "low")).toBe("low");
    expect(calculatePriority("low", "high")).toBe("medium");
    expect(calculatePriority("low", "medium")).toBe("low");
  });
});

describe("bumpPriority", () => {
  it("moves one step up the low -> normal -> medium -> high -> critical scale", () => {
    expect(bumpPriority("low")).toBe("normal");
    expect(bumpPriority("normal")).toBe("medium");
    expect(bumpPriority("medium")).toBe("high");
    expect(bumpPriority("high")).toBe("critical");
  });

  it("caps at critical", () => {
    expect(bumpPriority("critical")).toBe("critical");
  });

  it("falls back to normal for an unrecognized priority", () => {
    expect(bumpPriority("not-a-priority")).toBe("normal");
  });
});
