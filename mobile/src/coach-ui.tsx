import React from "react";
import { Pressable, StyleProp, Text, View, ViewStyle } from "react-native";
import Svg, { Circle, Line, Path, Rect } from "react-native-svg";

import type { ActiveAnalysisJob, PostureSignal } from "./contracts";
import { colors, fonts, formatValue, spacing, styles } from "./theme";

export const featureOrder = ["vertical", "elbow", "trunk", "lean"];

const featureMeta: Record<string, { label: string; short: string }> = {
  vertical: { label: "수직 진동", short: "수직진동" },
  elbow: { label: "팔꿈치 각도", short: "팔꿈치" },
  trunk: { label: "몸통 자세", short: "몸통" },
  lean: { label: "전방 기울기", short: "전방기울기" },
};

function normalizedId(value: string) {
  const id = value.toLowerCase();
  if (id.includes("vertical")) return "vertical";
  if (id.includes("elbow")) return "elbow";
  if (id.includes("trunk")) return "trunk";
  if (id.includes("lean")) return "lean";
  return id;
}

export type DisplaySignal = PostureSignal & { displayId: string; short: string };

export function displaySignals(signals: PostureSignal[]): DisplaySignal[] {
  const byId = new Map(signals.map((signal) => [normalizedId(signal.featureId), signal]));
  return featureOrder.map((displayId) => {
    const found = byId.get(displayId);
    const meta = featureMeta[displayId] ?? { label: displayId, short: displayId };
    return {
      featureId: found?.featureId ?? displayId,
      displayId,
      label: found?.label || meta.label,
      short: meta.short,
      priority: found?.priority ?? null,
      verdict: found?.verdict ?? "review",
      value: found?.value ?? null,
      unit: found?.unit ?? (displayId === "vertical" ? "cm" : "°"),
      referenceRange: found?.referenceRange ?? null,
      message: found?.message ?? "분석 결과가 쌓이면 이곳에 표시됩니다.",
      confidencePct: found?.confidencePct ?? null,
      confidenceLevel: found?.confidenceLevel ?? "excluded",
    };
  });
}

export function ProfileChip({ height, onPress }: { height: string; onPress: () => void }) {
  return (
    <Pressable
      accessibilityLabel="프로필 설정"
      accessibilityRole="button"
      onPress={onPress}
      style={({ pressed }) => ({
        alignItems: "center",
        backgroundColor: colors.surfaceSecondary,
        borderColor: colors.border,
        borderWidth: 1,
        justifyContent: "center",
        minHeight: 48,
        minWidth: 58,
        opacity: pressed ? 0.72 : 1,
        paddingHorizontal: spacing.sm,
      })}
    >
      <Text style={{ color: colors.lime, fontFamily: fonts.mono, fontSize: 14, fontWeight: "900" }}>
        {height || "—"}<Text style={{ color: colors.muted, fontSize: 9 }}> cm</Text>
      </Text>
    </Pressable>
  );
}

export function SectionHeading({ label, meta, onPress }: { label: string; meta?: string; onPress?: () => void }) {
  const content = <Text style={{ color: colors.muted, fontFamily: fonts.mono, fontSize: 10 }}>{meta}</Text>;
  return (
    <View style={{ alignItems: "center", flexDirection: "row", justifyContent: "space-between" }}>
      <Text style={{ color: colors.primary, fontSize: 13, fontWeight: "800" }}>{label}</Text>
      {onPress ? <Pressable accessibilityRole="button" onPress={onPress} style={{ justifyContent: "center", minHeight: 44 }}>{content}</Pressable> : content}
    </View>
  );
}

export function ScoreOverview({ jobs, onPress }: { jobs: ActiveAnalysisJob[]; onPress: () => void }) {
  const scored = jobs.filter((job) => job.status === "SUCCESS" && typeof job.postureScore === "number").slice(0, 4).reverse();
  const latest = scored.at(-1)?.postureScore ?? null;
  const points = scored.length > 1
    ? scored.map((job, index) => {
        const x = (index / (scored.length - 1)) * 120;
        const y = 6 + ((100 - (job.postureScore ?? 0)) / 100) * 34;
        return `${index ? "L" : "M"} ${x} ${y}`;
      }).join(" ")
    : "M 0 24 L 120 24";
  return (
    <View style={{ backgroundColor: colors.surfaceSecondary, borderColor: colors.border, borderWidth: 1, marginTop: spacing.md, padding: 14 }}>
      <SectionHeading label="내 자세 한눈에 보기" meta="최근 기록 →" onPress={onPress} />
      <View style={{ alignItems: "center", flexDirection: "row", gap: spacing.md, marginTop: spacing.md }}>
        <Text style={{ color: colors.lime, fontFamily: fonts.mono, fontSize: 39, fontWeight: "900" }}>
          {latest === null ? "—" : Math.round(latest)}<Text style={{ color: colors.muted, fontSize: 10 }}>/100</Text>
        </Text>
        <View style={{ flex: 1 }}>
          <Text style={{ color: colors.primary, fontSize: 12, fontWeight: "800" }}>이번 종합 자세 점수</Text>
          <Text style={[styles.caption, { marginTop: 4 }]}>3개 자세 피처 평균</Text>
        </View>
        <Svg accessibilityLabel="최근 종합 자세 점수 추이" height={46} role="img" viewBox="0 0 120 46" width={112}>
          <Line stroke={colors.border} x1="0" x2="120" y1="40" y2="40" />
          <Path d={points} fill="none" stroke={colors.primary} strokeWidth="2" />
          {scored.length ? <Circle cx="120" cy={6 + ((100 - (latest ?? 0)) / 100) * 34} fill={colors.lime} r="3.5" /> : null}
        </Svg>
      </View>
    </View>
  );
}

export function ImprovementChips({ signals, onPress }: { signals: PostureSignal[]; onPress: () => void }) {
  const priorities = signals.filter((signal) => signal.verdict === "improve").sort((a, b) => (a.priority ?? 99) - (b.priority ?? 99)).slice(0, 2);
  const items = priorities.length ? priorities : [
    { featureId: "trunk", label: "몸통 각도 범위 늘리기", message: "" },
    { featureId: "elbow", label: "팔꿈치 70–110° 유지", message: "" },
  ];
  return (
    <View style={{ flexDirection: "row", gap: 6, marginTop: 7 }}>
      {items.map((signal, index) => (
        <Pressable key={signal.featureId} accessibilityRole="button" onPress={onPress} style={({ pressed }) => ({ alignItems: "center", backgroundColor: colors.surface, borderColor: colors.border, borderWidth: 1, flex: 1, flexDirection: "row", gap: 7, minHeight: 48, opacity: pressed ? 0.72 : 1, paddingHorizontal: 9 })}>
          <Text style={{ color: colors.amber, fontFamily: fonts.mono, fontSize: 9, fontWeight: "900" }}>0{index + 1}</Text>
          <Text numberOfLines={2} style={{ color: colors.primary, flex: 1, fontSize: 10, fontWeight: "700", lineHeight: 14 }}>{signal.message || signal.label}</Text>
        </Pressable>
      ))}
    </View>
  );
}

export function FeatureTabs({ items, selected, onSelect }: { items: DisplaySignal[]; selected: string; onSelect: (id: string) => void }) {
  return (
    <View style={{ borderColor: colors.border, borderWidth: 1, flexDirection: "row", marginTop: 10 }}>
      {items.map((item, index) => {
        const active = item.displayId === selected;
        return <Pressable key={item.displayId} onPress={() => onSelect(item.displayId)} style={{ alignItems: "center", backgroundColor: active ? colors.lime : colors.background, borderRightColor: colors.border, borderRightWidth: index < items.length - 1 ? 1 : 0, flex: 1, justifyContent: "center", minHeight: 44 }}><Text style={{ color: active ? colors.limeInk : colors.muted, fontSize: 9, fontWeight: "800" }}>{item.short}</Text></Pressable>;
      })}
    </View>
  );
}

function signalTone(signal: PostureSignal) {
  if (signal.verdict === "improve") return colors.amber;
  if (signal.verdict === "maintain") return colors.lime;
  return colors.muted;
}

export function signalStatus(signal: PostureSignal) {
  if (signal.value === null) return "데이터 없음";
  if (signal.verdict === "improve") return "조정 필요";
  if (signal.verdict === "maintain") return "좋은 구간";
  return "검토 중";
}

export function SignalReading({ signal }: { signal: DisplaySignal }) {
  const range = signal.referenceRange;
  const score = signal.confidencePct === null ? null : Math.round(signal.confidencePct);
  if (signal.displayId === "vertical" || !range || signal.value === null) {
    return (
      <View style={{ marginTop: 12 }}>
        <View style={{ alignItems: "flex-end", flexDirection: "row", justifyContent: "space-between" }}>
          <View><Text style={{ color: colors.primary, fontSize: 14, fontWeight: "800" }}>{signal.label}</Text><Text style={{ color: signalTone(signal), fontSize: 10, marginTop: 5 }}>{signalStatus(signal)}</Text></View>
          <View style={{ alignItems: "flex-end" }}><Text style={{ color: colors.lime, fontFamily: fonts.mono, fontSize: 22, fontWeight: "900" }}>{score ?? "—"}<Text style={{ color: colors.muted, fontSize: 8 }}>/100</Text></Text><Text style={styles.caption}>측정 구간 평균값</Text></View>
        </View>
        <View style={{ alignItems: "center", flexDirection: "row", gap: 9, marginTop: 14 }}><Text style={styles.caption}>4cm</Text><View style={{ backgroundColor: colors.surfaceRaised, flex: 1, height: 7 }}><View style={{ backgroundColor: colors.lime, height: 15, left: signal.value === null ? "2%" : "55%", marginTop: -4, position: "absolute", width: 3 }} /></View><Text style={styles.caption}>12cm</Text></View>
        <Text style={{ color: colors.lime, fontFamily: fonts.mono, fontSize: 22, fontWeight: "900", marginTop: 9, textAlign: "center" }}>{formatValue(signal.value, signal.unit)}</Text>
      </View>
    );
  }
  const span = range.max - range.min || 1;
  const domainMin = Math.min(0, range.min - span);
  const domainMax = range.max + span;
  const marker = Math.max(0, Math.min(100, ((signal.value - domainMin) / (domainMax - domainMin)) * 100));
  const bandLeft = ((range.min - domainMin) / (domainMax - domainMin)) * 100;
  const bandWidth = ((range.max - range.min) / (domainMax - domainMin)) * 100;
  return (
    <View style={{ marginTop: 12 }}>
      <View style={{ alignItems: "flex-end", flexDirection: "row", justifyContent: "space-between" }}>
        <View><Text style={{ color: colors.primary, fontSize: 14, fontWeight: "800" }}>{signal.label}</Text><Text style={{ color: signalTone(signal), fontSize: 10, marginTop: 5 }}>{signalStatus(signal)}</Text></View>
        <View style={{ alignItems: "flex-end" }}><Text style={{ color: colors.lime, fontFamily: fonts.mono, fontSize: 22, fontWeight: "900" }}>{score ?? "—"}<Text style={{ color: colors.muted, fontSize: 8 }}>/100</Text></Text><Text style={styles.caption}>좋은 구간 프레임 비율</Text></View>
      </View>
      <View style={{ marginTop: 14 }}>
        <View style={{ backgroundColor: colors.surfaceRaised, height: 52, overflow: "hidden", position: "relative" }}>
          <View style={{ backgroundColor: "rgba(201,255,56,0.13)", height: "100%", left: `${bandLeft}%`, position: "absolute", width: `${bandWidth}%` }} />
          <View style={{ backgroundColor: colors.primary, height: 2, left: "3%", position: "absolute", right: "3%", top: 25, transform: [{ rotate: "-2deg" }] }} />
          <View style={{ backgroundColor: colors.lime, borderRadius: 4, height: 8, left: `${marker}%`, marginLeft: -4, position: "absolute", top: 22, width: 8 }} />
        </View>
        <View style={{ flexDirection: "row", justifyContent: "space-between", marginTop: 5 }}><Text style={styles.caption}>F01</Text><Text style={styles.caption}>좋은 구간 {formatValue(range.min, range.unit)}–{formatValue(range.max, range.unit)}</Text><Text style={styles.caption}>F84</Text></View>
      </View>
    </View>
  );
}

export function SignalStrip({ items, onSelect }: { items: DisplaySignal[]; onSelect: (id: string) => void }) {
  return (
    <View style={{ borderColor: colors.border, borderWidth: 1, flexDirection: "row", marginTop: 7 }}>
      {items.map((item, index) => <Pressable key={item.displayId} onPress={() => onSelect(item.displayId)} style={{ alignItems: "center", borderRightColor: colors.border, borderRightWidth: index < items.length - 1 ? 1 : 0, flex: 1, minHeight: 72, paddingHorizontal: 4, paddingVertical: 9 }}><Text style={{ color: colors.muted, fontSize: 8 }}>{item.short}</Text><Text style={{ color: colors.primary, fontFamily: fonts.mono, fontSize: 16, fontWeight: "900", marginTop: 5 }}>{item.confidencePct === null ? "—" : Math.round(item.confidencePct)}</Text><Text style={{ color: signalTone(item), fontSize: 7, marginTop: 5 }}>{signalStatus(item)}</Text></Pressable>)}
    </View>
  );
}

export function FullLink({ label, onPress, style }: { label: string; onPress: () => void; style?: StyleProp<ViewStyle> }) {
  return <Pressable accessibilityRole="button" onPress={onPress} style={({ pressed }) => [{ alignItems: "center", borderBottomColor: colors.border, borderBottomWidth: 1, borderTopColor: colors.border, borderTopWidth: 1, flexDirection: "row", justifyContent: "space-between", minHeight: 52, opacity: pressed ? 0.7 : 1, paddingHorizontal: 4 }, style]}><Text style={{ color: colors.primary, fontSize: 11, fontWeight: "800" }}>{label}</Text><Text style={{ color: colors.lime }}>→</Text></Pressable>;
}
