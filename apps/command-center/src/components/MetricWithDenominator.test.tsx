import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { MetricWithDenominator } from "./MetricWithDenominator";

describe("MetricWithDenominator", () => {
  it("renders value with explicit denominator", () => {
    render(
      <MetricWithDenominator
        label="Top 20 com cadastro oficial"
        value={20}
        denominator={20}
        unitLabel="universo Top 20"
      />,
    );
    expect(screen.getByText("Top 20 com cadastro oficial")).toBeInTheDocument();
    expect(screen.getByText(/de 20/)).toBeInTheDocument();
    expect(screen.getByText("universo Top 20")).toBeInTheDocument();
  });
});
