import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { BRAND_LOGO_SHA256, BRAND_LOGO_SRC, BrandLogo } from "./BrandLogo";

describe("BrandLogo", () => {
  it("loads the canonical official asset path and checksum marker", () => {
    render(<BrandLogo height={40} />);
    const img = screen.getByRole("img", { name: "CONFENGE" });
    expect(img.getAttribute("src")).toBe(BRAND_LOGO_SRC);
    expect(img.getAttribute("data-brand-sha256")).toBe(BRAND_LOGO_SHA256);
    expect(BRAND_LOGO_SHA256).toBe(
      "e6af0125c73edd476cff82ab4ea1de3e459fbdbde63b886f6c55f8a93531505b",
    );
    expect(img.getAttribute("width")).toBeTruthy();
    expect(img.getAttribute("height")).toBe("40");
  });

  it("wraps official logo in a light plate when requested (dark sidebar)", () => {
    const { container } = render(<BrandLogo plate height={40} />);
    expect(container.querySelector(".brand-logo-plate")).toBeTruthy();
    expect(screen.getByRole("img", { name: "CONFENGE" }).getAttribute("src")).toBe(
      "/brand/logo-confenge.png",
    );
  });
});
