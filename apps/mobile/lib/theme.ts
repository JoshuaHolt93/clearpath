// Minimal mobile theme. This is intentionally small for the scaffold; on a later
// slice it should be derived from @clearpath/design-tokens so web and mobile
// share one visual language (see MOBILE.md "Design system"). The accent and
// neutrals below match the web app's landing/auth palette.
export const theme = {
  color: {
    accent: "#2d6cdf",
    accentText: "#ffffff",
    background: "#f4f6fa",
    surface: "#ffffff",
    border: "#dde2ea",
    text: "#1f2733",
    textSecondary: "#3d4453",
    textMuted: "#5b6472",
    danger: "#c2413b",
    success: "#1f7a4d",
  },
  spacing: (units: number) => units * 8,
  radius: { sm: 8, md: 12, lg: 16 },
} as const;

export type Theme = typeof theme;
