/** CONFENGE brand mark (sourced from webcfg assets/logo-confenge*.png). */

export function BrandLogo({
  variant = "auto",
  className = "",
  height = 28,
}: {
  variant?: "color" | "white" | "auto";
  className?: string;
  height?: number;
}) {
  // SVG wordmarks (reviewability-safe). Visual identity aligned with webcfg brand tokens.
  const colorSrc = "/brand/logo-confenge.svg";
  const whiteSrc = "/brand/logo-confenge-white.svg";
  if (variant === "color") {
    return (
      <img
        src={colorSrc}
        alt="CONFENGE"
        className={`brand-logo ${className}`.trim()}
        height={height}
        width={Math.round(height * (800 / 208))}
        decoding="async"
      />
    );
  }
  if (variant === "white") {
    return (
      <img
        src={whiteSrc}
        alt="CONFENGE"
        className={`brand-logo ${className}`.trim()}
        height={height}
        width={Math.round(height * (800 / 208))}
        decoding="async"
      />
    );
  }
  // auto: show color in light, white in dark (CSS swaps visibility)
  return (
    <span className={`brand-logo-pair ${className}`.trim()} aria-label="CONFENGE">
      <img
        src={colorSrc}
        alt=""
        className="brand-logo brand-logo--light"
        height={height}
        width={Math.round(height * (800 / 208))}
        decoding="async"
      />
      <img
        src={whiteSrc}
        alt=""
        className="brand-logo brand-logo--dark"
        height={height}
        width={Math.round(height * (800 / 208))}
        decoding="async"
      />
    </span>
  );
}
