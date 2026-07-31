/**
 * CONFENGE brand mark — official raster asset only.
 * Source of truth: tjsasakifln/web-cfg assets/logo-confenge.png
 * SHA-256: e6af0125c73edd476cff82ab4ea1de3e459fbdbde63b886f6c55f8a93531505b
 * No SVG redesigns, no CSS invert/filter white variants.
 */

/** Official aspect ratio of web-cfg logo-confenge.png (800×208). */
export const BRAND_LOGO_ASPECT = 800 / 208;
export const BRAND_LOGO_SRC = "/brand/logo-confenge.png";
/** Canonical checksum of the official asset (tests pin this). */
export const BRAND_LOGO_SHA256 =
  "e6af0125c73edd476cff82ab4ea1de3e459fbdbde63b886f6c55f8a93531505b";

export function BrandLogo({
  className = "",
  height = 44,
  plate = false,
}: {
  className?: string;
  height?: number;
  /** Light neutral plate for dark sidebar — does not recolor the logo. */
  plate?: boolean;
}) {
  const width = Math.round(height * BRAND_LOGO_ASPECT);
  const img = (
    <img
      src={BRAND_LOGO_SRC}
      alt="CONFENGE"
      className={`brand-logo ${className}`.trim()}
      height={height}
      width={width}
      decoding="async"
      data-brand-src={BRAND_LOGO_SRC}
      data-brand-sha256={BRAND_LOGO_SHA256}
    />
  );
  if (!plate) return img;
  return <span className="brand-logo-plate">{img}</span>;
}
