import { Platform, StyleSheet } from "react-native";

export const colors = {
  background: "#090b0a",
  surface: "#111411",
  surfaceSecondary: "#181c19",
  surfaceRaised: "#202521",
  border: "#343a35",
  muted: "#939991",
  secondary: "#d9ddd6",
  primary: "#f3f4ef",
  lime: "#c9ff38",
  limeInk: "#0b1700",
  amber: "#ffc867",
  red: "#ff7e6d",
};

export const spacing = {
  xs: 4,
  sm: 8,
  md: 12,
  lg: 16,
  xl: 20,
  xxl: 24,
  xxxl: 32,
};

export const fonts = {
  sans: Platform.select({
    ios: "System",
    android: "sans-serif",
    default: "System",
  }),
  mono: Platform.select({
    ios: "Menlo",
    android: "monospace",
    default: "monospace",
  }),
};

export const styles = StyleSheet.create({
  screen: {
    flex: 1,
    backgroundColor: colors.background,
  },
  content: {
    paddingHorizontal: 17,
    paddingBottom: 96,
  },
  eyebrow: {
    color: colors.lime,
    fontFamily: fonts.mono,
    fontSize: 11,
    letterSpacing: 1.2,
    textTransform: "uppercase",
  },
  title: {
    color: colors.primary,
    fontSize: 23,
    fontWeight: "900",
    letterSpacing: -0.55,
    lineHeight: 29,
  },
  subtitle: {
    color: colors.secondary,
    fontSize: 14,
    lineHeight: 21,
  },
  body: {
    color: colors.secondary,
    fontSize: 13,
    lineHeight: 20,
  },
  caption: {
    color: colors.muted,
    fontSize: 12,
    lineHeight: 18,
  },
  mono: {
    color: colors.primary,
    fontFamily: fonts.mono,
  },
  panel: {
    backgroundColor: colors.surface,
    borderColor: colors.border,
    borderWidth: 1,
    padding: 14,
  },
  button: {
    alignItems: "center",
    flexDirection: "row",
    justifyContent: "center",
    minHeight: 52,
    paddingHorizontal: spacing.lg,
  },
  primaryButton: {
    backgroundColor: colors.lime,
  },
  secondaryButton: {
    backgroundColor: colors.surfaceRaised,
    borderColor: colors.border,
    borderWidth: 1,
  },
  buttonText: {
    fontSize: 15,
    fontWeight: "800",
  },
});

export function formatValue(value: number | null, unit = "") {
  if (value === null || !Number.isFinite(value)) return "—";
  const formatted = Number.isInteger(value)
    ? String(value)
    : value.toFixed(Math.abs(value) < 1 ? 3 : 1).replace(/0+$/, "").replace(/\.$/, "");
  return `${formatted}${unit ? ` ${unit}` : ""}`;
}

export function formatDate(value: string | null) {
  if (!value) return "날짜 없음";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("ko-KR", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}
