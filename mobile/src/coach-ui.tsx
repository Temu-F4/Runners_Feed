import React from "react";
import { Pressable, StyleProp, Text, View, ViewStyle } from "react-native";
import Svg, { Circle, Line, Path, Rect } from "react-native-svg";

import type { ActiveAnalysisJob, PostureSignal, ReferenceRange } from "./contracts";
import { colors, fonts, formatValue, spacing, styles } from "./theme";
import { displaySignals, scoreCohortJobs, signalScore, type DisplaySignal } from "./signal-data";

export { displaySignals } from "./signal-data";

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
  const scored = scoreCohortJobs(jobs).slice(0, 4).reverse();
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
  const maintain = signals.filter((signal) => signal.verdict === "maintain").slice(0, 2);
  const items = priorities.length ? priorities : maintain;
  if (!items.length) {
    return <View style={{ borderColor: colors.border, borderWidth: 1, marginTop: 7, minHeight: 48, padding: 10 }}><Text style={styles.caption}>표시할 개인 분석 결과가 아직 없습니다.</Text></View>;
  }
  return (
    <View style={{ flexDirection: "row", gap: 6, marginTop: 7 }}>
      {items.map((signal, index) => (
        <Pressable key={signal.featureId} accessibilityRole="button" onPress={onPress} style={({ pressed }) => ({ alignItems: "center", backgroundColor: colors.surface, borderColor: colors.border, borderWidth: 1, flex: 1, flexDirection: "row", gap: 7, minHeight: 48, opacity: pressed ? 0.72 : 1, paddingHorizontal: 9 })}>
          <Text style={{ color: colors.amber, fontFamily: fonts.mono, fontSize: 9, fontWeight: "900" }}>0{index + 1}</Text>
          <Text numberOfLines={2} style={{ color: colors.primary, flex: 1, fontSize: 10, fontWeight: "700", lineHeight: 14 }}>{signal.verdict === "improve" ? `${signal.label} 자세를 조정해 보세요` : `${signal.label} 자세가 좋습니다`}</Text>
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
  if (signal.value === null || signal.verdict === "unavailable") return "측정 불가";
  if (signal.featureId === "feature1") {
    const range = signal.referenceRange;
    return range && signal.value >= range.min && signal.value <= range.max ? "관찰 범위 안" : "관찰 범위 밖";
  }
  if (signal.verdict === "improve") return "조정 필요";
  if (signal.verdict === "maintain") return "좋은 구간";
  return "검토 중";
}

function DynamicRangeBar({ value, range }: { value: number; range: ReferenceRange }) {
  const span = Math.max(range.max - range.min, 0.000001);
  const domainMin = Math.min(range.min - span, value - span * 0.2);
  const domainMax = Math.max(range.max + span, value + span * 0.2);
  const domainSpan = domainMax - domainMin;
  const bandLeft = ((range.min - domainMin) / domainSpan) * 100;
  const bandWidth = ((range.max - range.min) / domainSpan) * 100;
  const marker = Math.max(0, Math.min(100, ((value - domainMin) / domainSpan) * 100));
  return <View style={{ marginTop: 14 }}><View style={{ backgroundColor: colors.surfaceRaised, height: 9, position: "relative" }}><View style={{ backgroundColor: "rgba(201,255,56,0.28)", height: "100%", left: `${bandLeft}%`, position: "absolute", width: `${bandWidth}%` }} /><View style={{ backgroundColor: colors.lime, height: 17, left: `${marker}%`, marginLeft: -2, marginTop: -4, position: "absolute", width: 4 }} /></View><View style={{ flexDirection: "row", justifyContent: "space-between", marginTop: 5 }}><Text style={styles.caption}>{formatValue(range.min, range.unit)}</Text><Text style={styles.caption}>관찰 범위</Text><Text style={styles.caption}>{formatValue(range.max, range.unit)}</Text></View></View>;
}

export function SignalReading({ signal }: { signal: DisplaySignal }) {
  const range = signal.referenceRange;
  const score = signalScore(signal);
  if (signal.displayId === "feature1" || !range || signal.value === null) {
    return (
      <View style={{ marginTop: 12 }}>
        <View style={{ alignItems: "flex-end", flexDirection: "row", justifyContent: "space-between" }}>
          <View><Text style={{ color: colors.primary, fontSize: 14, fontWeight: "800" }}>{signal.label}</Text><Text style={{ color: signalTone(signal), fontSize: 10, marginTop: 5 }}>{signalStatus(signal)}</Text></View>
          <View style={{ alignItems: "flex-end" }}><Text style={{ color: colors.lime, fontFamily: fonts.mono, fontSize: 22, fontWeight: "900" }}>{formatValue(signal.value, signal.unit)}</Text><Text style={styles.caption}>{signal.displayId === "feature1" ? "점수 없음 · 관찰값" : "측정값"}</Text></View>
        </View>
        {range && signal.value !== null ? <DynamicRangeBar value={signal.value} range={range} /> : null}
      </View>
    );
  }
  return (
    <View style={{ marginTop: 12 }}>
      <View style={{ alignItems: "flex-end", flexDirection: "row", justifyContent: "space-between" }}>
        <View><Text style={{ color: colors.primary, fontSize: 14, fontWeight: "800" }}>{signal.label}</Text><Text style={{ color: signalTone(signal), fontSize: 10, marginTop: 5 }}>{signalStatus(signal)}</Text></View>
        <View style={{ alignItems: "flex-end" }}><Text style={{ color: colors.lime, fontFamily: fonts.mono, fontSize: score === null ? 14 : 22, fontWeight: "900" }}>{score === null ? "점수 없음" : <>{score}<Text style={{ color: colors.muted, fontSize: 8 }}>/100</Text></>}</Text><Text style={styles.caption}>좋은 구간 프레임 비율</Text></View>
      </View>
      <Text style={{ color: colors.primary, fontFamily: fonts.mono, fontSize: 16, fontWeight: "800", marginTop: 10 }}>{formatValue(signal.value, signal.unit)}</Text>
      <DynamicRangeBar value={signal.value} range={range} />
    </View>
  );
}

export function SignalStrip({ items, onSelect }: { items: DisplaySignal[]; onSelect: (id: string) => void }) {
  return (
    <View style={{ borderColor: colors.border, borderWidth: 1, flexDirection: "row", marginTop: 7 }}>
      {items.map((item, index) => { const score = signalScore(item); return <Pressable key={item.displayId} onPress={() => onSelect(item.displayId)} style={{ alignItems: "center", borderRightColor: colors.border, borderRightWidth: index < items.length - 1 ? 1 : 0, flex: 1, minHeight: 72, paddingHorizontal: 4, paddingVertical: 9 }}><Text style={{ color: colors.muted, fontSize: 8 }}>{item.short}</Text><Text style={{ color: colors.primary, fontFamily: fonts.mono, fontSize: 13, fontWeight: "900", marginTop: 5 }}>{item.displayId === "feature1" ? formatValue(item.value, item.unit) : score === null ? "점수 없음" : `${score}점`}</Text><Text style={{ color: signalTone(item), fontSize: 7, marginTop: 5 }}>{signalStatus(item)}</Text></Pressable>; })}
    </View>
  );
}

export function FullLink({ label, onPress, style }: { label: string; onPress: () => void; style?: StyleProp<ViewStyle> }) {
  return <Pressable accessibilityRole="button" onPress={onPress} style={({ pressed }) => [{ alignItems: "center", borderBottomColor: colors.border, borderBottomWidth: 1, borderTopColor: colors.border, borderTopWidth: 1, flexDirection: "row", justifyContent: "space-between", minHeight: 52, opacity: pressed ? 0.7 : 1, paddingHorizontal: 4 }, style]}><Text style={{ color: colors.primary, fontSize: 11, fontWeight: "800" }}>{label}</Text><Text style={{ color: colors.lime }}>→</Text></Pressable>;
}
