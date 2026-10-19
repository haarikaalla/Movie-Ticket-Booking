import { describe, expect, it } from "vitest";
import { calculateTotal } from "./pricing";

describe("calculateTotal", () => {
  it("adds mixed seat tiers without mutating the selection", () => {
    const seats = [{ price: 220 }, { price: 280 }, { price: 340 }];

    expect(calculateTotal(seats)).toBe(840);
    expect(seats).toHaveLength(3);
  });

  it("returns zero for an empty selection", () => {
    expect(calculateTotal([])).toBe(0);
  });
});
