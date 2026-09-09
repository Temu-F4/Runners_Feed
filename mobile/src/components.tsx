import React from "react";
import {
  ActivityIndicator,
  Pressable,
  RefreshControlProps,
  ScrollView,
  StyleProp,
  Text,
  TextInput,
  TextInputProps,
  View,
  ViewStyle,
} from "react-native";
import { usePathname, useRouter } from "expo-router";
import Svg, { Circle, Line, Path, Rect } from "react-native-svg";

import type {
  ActiveAnalysisJob,
  FeatureAnalysis,
  JobStage,
  PostureSignal,
  TrendSummary,
} from "./contracts";
import { colors, formatDate, formatValue, spacing, styles } from "./theme";
import { featureScore, featureScoreLabel } from "./scoring";
import { scoreCohortJobs } from "./signal-data";

export function Screen({
  children,
  contentStyle,
  refreshControl,
}: {
  children: React.ReactNode;
  contentStyle?: StyleProp<ViewStyle>;
  refreshControl?: React.ReactElement<RefreshControlProps>;
}) {
  return (
    <ScrollView
      style={styles.screen}
      contentContainerStyle={[styles.content, contentStyle]}
      refreshControl={refreshControl}
      showsVerticalScrollIndicator={false}
    >
      {children}
    </ScrollView>
  );
}

export function AppHeader({
  eyebrow = "RUNNERS FEED",
  title,
  right,
}: {
  eyebrow?: string;
  title: string;
  right?: React.ReactNode;
}) {
  return (
    <View style={{ paddingBottom: 14, paddingTop: 18 }}>
      <View style={{ alignItems: "center", flexDirection: "row", justifyContent: "space-between" }}>
        <View style={{ flex: 1, gap: 6, paddingRight: spacing.sm }}>
          <Text style={styles.eyebrow}>{eyebrow}</Text>
          <Text style={styles.title}>{title}</Text>
        </View>
        {right}
      </View>
    </View>
  );
}

export function Panel({ children, style }: { children: React.ReactNode; style?: StyleProp<ViewStyle> }) {
  return <View style={[styles.panel, style]}>{children}</View>;
}

export function Button({
  label,
  onPress,
  kind = "primary",
  disabled = false,
  loading = false,
  style,
}: {
  label: string;
  onPress: () => void;
  kind?: "primary" | "secondary";
  disabled?: boolean;
  loading?: boolean;
  style?: StyleProp<ViewStyle>;
}) {
  const unavailable = disabled || loading;
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ disabled: unavailable, busy: loading }}
      disabled={unavailable}
      onPress={onPress}
      style={({ pressed }) => [
        styles.button,
        kind === "primary" ? styles.primaryButton : styles.secondaryButton,
        unavailable && { opacity: 0.45 },
        pressed && !unavailable && { opacity: 0.75 },
        style,
      ]}
    >
      {loading ? (
        <ActivityIndicator color={kind === "primary" ? colors.limeInk : colors.lime} />
      ) : (
        <Text style={[styles.buttonText, { color: kind === "primary" ? colors.limeInk : colors.primary }]}>
          {label}
        </Text>
      )}
    </Pressable>
  );
}

export function TextField({ label, error, ...props }: TextInputProps & { label: string; error?: string }) {
  return (
    <View style={{ gap: spacing.sm }}>
      <Text style={styles.caption}>{label}</Text>
      <TextInput
        {...props}
        accessibilityLabel={props.accessibilityLabel ?? label}
        placeholderTextColor={colors.muted}
        style={{
          backgroundColor: colors.surfaceSecondary,
          borderColor: error ? colors.red : colors.border,
          borderRadius: 2,
          borderWidth: 1,
          color: colors.primary,
          fontFamily: styles.mono.fontFamily,
          fontSize: 16,
          minHeight: 52,
          paddingHorizontal: spacing.md,
        }}
      />
      {error ? <Text style={{ color: colors.red, fontSize: 12 }}>{error}</Text> : null}
    </View>
  );
}

export function StatusBadge({ status, label }: { status: string; label?: string }) {
  const isDanger = status === "FAILED" || status === "ERROR" || status === "improve";
  const isActive = status === "PROCESSING" || status === "QUEUED";
  const isGood = status === "maintain";
  return (
    <View
      style={{
        alignSelf: "flex-start",
        backgroundColor: isDanger ? "#3a1e1a" : isGood ? "#26320e" : isActive ? "#26320e" : colors.surfaceRaised,
        borderColor: isDanger ? colors.red : isGood || isActive ? colors.lime : colors.border,
        borderRadius: 2,
        borderWidth: 1,
        paddingHorizontal: spacing.sm,
        paddingVertical: 6,
      }}
    >
      <Text
        style={{
          color: isDanger ? colors.red : isGood || isActive ? colors.lime : colors.secondary,
          fontFamily: styles.mono.fontFamily,
          fontSize: 11,
          fontWeight: "700",
        }}
      >
        {label ?? status}
      </Text>
    </View>
  );
}

export function LoadingState({ message = "불러오는 중입니다." }: { message?: string }) {
  return (
    <View style={{ alignItems: "center", gap: spacing.md, paddingVertical: spacing.xxxl }}>
      <ActivityIndicator color={colors.lime} />
      <Text style={styles.caption}>{message}</Text>
    </View>
  );
}

export function EmptyState({ title, message }: { title: string; message: string }) {
  return (
    <Panel>
      <Text style={{ color: colors.primary, fontSize: 17, fontWeight: "700" }}>{title}</Text>
      <Text style={[styles.body, { marginTop: spacing.sm }]}>{message}</Text>
    </Panel>
  );
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <Panel style={{ borderColor: colors.red }}>
      <Text style={{ color: colors.red, fontSize: 17, fontWeight: "700" }}>문제가 발생했습니다</Text>
      <Text style={[styles.body, { marginTop: spacing.sm }]}>{message}</Text>
      {onRetry ? <Button label="다시 시도" onPress={onRetry} kind="secondary" style={{ marginTop: spacing.lg }} /> : null}
    </Panel>
  );
}

const stageLabels: Record<JobStage, string> = {
  upload: "업로드 중",
  queue: "분석 대기 중",
  keypoints: "움직임 분석 중",
  features: "결과 정리 중",
  validation: "결과 정리 중",
  result: "완료",
};

export function stageLabel(stage: JobStage) {
  return stageLabels[stage];
}

export function ProgressBar({ value }: { value: number | null }) {
  const width = value === null ? 8 : Math.max(4, Math.min(100, value));
  return (
    <View style={{ backgroundColor: colors.surfaceRaised, borderRadius: 2, height: 8, overflow: "hidden" }}>
      <View style={{ backgroundColor: colors.lime, height: "100%", width: `${width}%` }} />
    </View>
  );
}

function statusLabel(status: ActiveAnalysisJob["status"]) {
  if (status === "SUCCESS") return "완료";
  if (status === "FAILED") return "실패";
  if (status === "ERROR") return "오류";
  if (status === "PROCESSING") return "분석 중";
  if (status === "QUEUED") return "대기 중";
  return status;
}

export function JobCard({ job, onPress }: { job: ActiveAnalysisJob; onPress: () => void }) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={`${job.title}, ${statusLabel(job.status)}`}
      onPress={onPress}
      style={({ pressed }) => [styles.panel, { gap: spacing.md, opacity: pressed ? 0.75 : 1 }]}
    >
      <View style={{ alignItems: "center", flexDirection: "row", justifyContent: "space-between" }}>
        <View style={{ flex: 1, gap: spacing.xs }}>
          <Text style={{ color: colors.primary, fontSize: 16, fontWeight: "700" }}>{job.title}</Text>
          <Text style={styles.caption}>{formatDate(job.createdAt)}</Text>
        </View>
        <View style={{ alignItems: "flex-end", gap: spacing.xs }}>
          {typeof job.postureScore === "number" ? <Text style={{ color: colors.lime, fontFamily: styles.mono.fontFamily, fontSize: 20, fontWeight: "900" }}>{Math.round(job.postureScore)}<Text style={{ color: colors.muted, fontSize: 10 }}>/100</Text></Text> : null}
          <StatusBadge status={job.status} label={statusLabel(job.status)} />
        </View>
      </View>
      <View style={{ gap: spacing.sm }}>
        <View style={{ alignItems: "center", flexDirection: "row", justifyContent: "space-between" }}>
          <Text style={styles.caption}>{stageLabel(job.stage)}</Text>
          <Text style={styles.mono}>{job.progressPct === null ? "—" : `${Math.round(job.progressPct)}%`}</Text>
        </View>
        <ProgressBar value={job.progressPct} />
        {job.status === "SUCCESS" ? <Text style={styles.caption}>{job.renderedVideoExpiresAt ? `렌더링 영상 ${formatDate(job.renderedVideoExpiresAt)}까지` : "스켈레톤 리포트 보관"}</Text> : null}
        {job.error ? <Text style={{ color: colors.red, fontSize: 12 }}>{job.error}</Text> : null}
      </View>
    </Pressable>
  );
}

export function ScoreTrendChart({ jobs }: { jobs: ActiveAnalysisJob[] }) {
  const scored = scoreCohortJobs(jobs)
    .slice(0, 8)
    .reverse();
  if (scored.length < 2) {
    return <Text style={styles.caption}>점수가 두 번 이상 쌓이면 날짜별 추이가 표시됩니다.</Text>;
  }
  const width = 320;
  const height = 120;
  const left = 12;
  const top = 20;
  const plotWidth = 296;
  const plotHeight = 66;
  const x = (index: number) => left + (index / Math.max(1, scored.length - 1)) * plotWidth;
  const y = (score: number) => top + ((100 - score) / 100) * plotHeight;
  const path = scored.map((job, index) => `${index ? "L" : "M"} ${x(index)} ${y(job.postureScore!)}`).join(" ");
  return (
    <View style={{ gap: spacing.sm }}>
      <Svg accessibilityLabel="날짜별 종합 자세 점수 추이" height={height} role="img" viewBox={`0 0 ${width} ${height}`} width="100%">
        <Line stroke={colors.border} strokeWidth="1" x1={left} x2={left + plotWidth} y1={top + plotHeight} y2={top + plotHeight} />
        <Path d={path} fill="none" stroke={colors.primary} strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" />
        {scored.map((job, index) => <Circle key={job.jobId} cx={x(index)} cy={y(job.postureScore!)} fill={colors.lime} r="4" />)}
      </Svg>
      <View style={{ flexDirection: "row", justifyContent: "space-between" }}>
        {scored.map((job) => <View key={job.jobId} style={{ alignItems: "center" }}><Text style={{ color: colors.primary, fontFamily: styles.mono.fontFamily, fontSize: 11, fontWeight: "800" }}>{Math.round(job.postureScore!)}</Text><Text style={styles.caption}>{new Date(job.createdAt).toLocaleDateString("ko-KR", { month: "2-digit", day: "2-digit" })}</Text></View>)}
      </View>
    </View>
  );
}

export function BottomNavigation() {
  const pathname = usePathname();
  const router = useRouter();
  const items = [
    { label: "홈", mark: "□", path: "/" as const },
    { label: "분석", mark: "+", path: "/upload" as const },
    { label: "기록", mark: "↗", path: "/history" as const },
  ];
  return (
    <View style={{ backgroundColor: colors.surface, borderColor: colors.border, borderTopWidth: 1, bottom: 0, flexDirection: "row", left: 0, paddingBottom: 8, paddingTop: 5, position: "absolute", right: 0 }}>
      {items.map((item) => {
        const active = item.path === "/" ? pathname === "/" : pathname.startsWith(item.path);
        return (
          <Pressable
            key={item.path}
            accessibilityRole="button"
            accessibilityState={{ selected: active }}
            onPress={() => router.push(item.path)}
            style={{ alignItems: "center", flex: 1, gap: 2, minHeight: 54, justifyContent: "center" }}
          >
            <Text style={{ color: active ? colors.lime : colors.muted, fontFamily: styles.mono.fontFamily, fontSize: 15, fontWeight: "800" }}>{item.mark}</Text>
            <Text style={{ color: active ? colors.lime : colors.muted, fontSize: 10, fontWeight: active ? "800" : "500" }}>{item.label}</Text>
          </Pressable>
        );
      })}
    </View>
  );
}

function chartValues(values: Array<number | null>) {
  return values.filter((value): value is number => value !== null && Number.isFinite(value));
}

function chartDomain(values: number[], referenceMin?: number, referenceMax?: number) {
  const all = [...values];
  if (referenceMin !== undefined) all.push(referenceMin);
  if (referenceMax !== undefined) all.push(referenceMax);
  const min = Math.min(...all);
  const max = Math.max(...all);
  const span = max > min ? max - min : Math.max(Math.abs(max) * 0.2, 1);
  return { min: min - span * 0.12, max: max + span * 0.12 };
}

function yPosition(value: number, min: number, max: number, top: number, height: number) {
  return top + ((max - value) / (max - min)) * height;
}

function seriesPath(
  values: Array<number | null>,
  min: number,
  max: number,
  left: number,
  top: number,
  width: number,
  height: number,
  xValues?: number[],
) {
  const paths: string[] = [];
  let path = "";
  values.forEach((value, index) => {
    if (value === null || !Number.isFinite(value)) {
      if (path) paths.push(path);
      path = "";
      return;
    }
    const xDomain = xValues && xValues.length === values.length ? xValues : values.map((_, itemIndex) => itemIndex);
    const xMin = Math.min(...xDomain);
    const xMax = Math.max(...xDomain);
    const x = left + (((xDomain[index] ?? xMin) - xMin) / Math.max(xMax - xMin, 1)) * width;
    const y = yPosition(value, min, max, top, height);
    path += path ? ` L ${x} ${y}` : `M ${x} ${y}`;
  });
  if (path) paths.push(path);
  return paths;
}

export function TrendChart({ trend }: { trend: TrendSummary | null }) {
  if (!trend || trend.points.length < 8) return null;
  const values = trend.points.map((point) => point.value);
  const valid = chartValues(values);
  if (valid.length < 2) return null;
  const width = 320;
  const height = 128;
  const left = 8;
  const top = 12;
  const plotWidth = 304;
  const plotHeight = 82;
  const domain = chartDomain(valid);
  const paths = seriesPath(values, domain.min, domain.max, left, top, plotWidth, plotHeight);
  return (
    <View style={{ gap: spacing.sm }}>
      <Svg accessibilityLabel={`${trend.label} 추세 그래프`} height={height} role="img" viewBox={`0 0 ${width} ${height}`} width="100%">
        <Line stroke={colors.border} strokeWidth="1" x1={left} x2={left + plotWidth} y1={top + plotHeight} y2={top + plotHeight} />
        <Line stroke={colors.surfaceRaised} strokeWidth="1" x1={left} x2={left + plotWidth} y1={top + plotHeight / 2} y2={top + plotHeight / 2} />
        {paths.map((path, index) => <Path d={path} fill="none" key={index} stroke={colors.lime} strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" />)}
      </Svg>
      <View style={{ flexDirection: "row", justifyContent: "space-between" }}>
        <Text style={styles.caption}>{formatDate(trend.points[0]?.recordedAt ?? null)}</Text>
        <Text style={styles.caption}>{formatDate(trend.points[trend.points.length - 1]?.recordedAt ?? null)}</Text>
      </View>
      <Text style={styles.caption}>{trend.summary ?? `${trend.label} · ${trend.unit}`}{trend.deltaPct === null ? "" : ` · ${trend.deltaPct >= 0 ? "+" : ""}${trend.deltaPct.toFixed(1)}%`}</Text>
    </View>
  );
}

export function RangeBar({ feature }: { feature: FeatureAnalysis }) {
  const range = feature.referenceRange;
  if (!range || feature.representativeValue === null || range.max <= range.min) {
    return <EmptyState title="기준 범위 없음" message="이 지표에는 현재 비교 가능한 기준 범위가 제공되지 않았습니다." />;
  }
  const span = range.max - range.min;
  const domainMin = Math.min(range.min - span, feature.representativeValue - span * 0.2);
  const domainMax = Math.max(range.max + span, feature.representativeValue + span * 0.2);
  const domainSpan = domainMax - domainMin;
  const left = ((range.min - domainMin) / domainSpan) * 100;
  const width = ((range.max - range.min) / domainSpan) * 100;
  const position = Math.max(0, Math.min(100, ((feature.representativeValue - domainMin) / domainSpan) * 100));
  return (
    <View style={{ gap: spacing.sm }}>
      <View accessible accessibilityLabel={`정상 범위 ${formatValue(range.min, range.unit)}에서 ${formatValue(range.max, range.unit)}, 현재 ${formatValue(feature.representativeValue, feature.unit)}`} style={{ backgroundColor: colors.surfaceRaised, height: 12, position: "relative" }}>
        <View style={{ backgroundColor: "rgba(201,255,56,0.28)", height: "100%", left: `${left}%`, position: "absolute", width: `${width}%` }} />
        <View style={{ backgroundColor: colors.lime, borderRadius: 8, height: 20, left: `${position}%`, marginLeft: -8, marginTop: -4, position: "absolute", width: 16 }} />
      </View>
      <View style={{ flexDirection: "row", justifyContent: "space-between" }}>
        <Text style={styles.caption}>{formatValue(range.min, range.unit)}</Text>
        <Text style={styles.caption}>정상 범위</Text>
        <Text style={styles.caption}>{formatValue(range.max, range.unit)}</Text>
      </View>
    </View>
  );
}

export function FeatureFrameChart({ feature }: { feature: FeatureAnalysis }) {
  const points = feature.series;
  const valid = points.filter((point) => point.value !== null && Number.isFinite(point.value));
  if (valid.length < 2) return <RangeBar feature={feature} />;
  const range = feature.referenceRange;
  const values = points.map((point) => point.value);
  const domain = chartDomain(chartValues(values), range?.min, range?.max);
  const width = 320;
  const height = 148;
  const left = 40;
  const top = 14;
  const plotWidth = 264;
  const plotHeight = 92;
  const evaluatedAxis = feature.visualization?.x_axis === "measurable_frame";
  const sourceEnd = Math.max(
    feature.sourceFrameCount ? feature.sourceFrameCount - 1 : 0,
    ...points.map((point) => point.frameIndex),
  );
  const xValues = evaluatedAxis
    ? points.map((_, index) => index)
    : points.map((point) => point.frameIndex);
  if (!evaluatedAxis && sourceEnd > 0) {
    // Anchor the domain to the full video so missing frames keep their real spacing.
    xValues.push(sourceEnd);
    values.push(null);
  }
  const paths = seriesPath(values, domain.min, domain.max, left, top, plotWidth, plotHeight, xValues);
  const lastPoint = valid[valid.length - 1]!;
  const bandTop = range ? yPosition(range.max, domain.min, domain.max, top, plotHeight) : null;
  const bandBottom = range ? yPosition(range.min, domain.min, domain.max, top, plotHeight) : null;
  const axisStart = evaluatedAxis ? 1 : (points[0]?.frameIndex ?? 1);
  const axisEnd = evaluatedAxis ? points.length : sourceEnd;
  const lastX = evaluatedAxis
    ? left + plotWidth
    : left + (lastPoint.frameIndex / Math.max(sourceEnd, 1)) * plotWidth;
  return (
    <View style={{ gap: spacing.xs }}>
      <Svg accessibilityLabel={`${feature.label} 프레임별 측정 그래프`} height={height} role="img" viewBox={`0 0 ${width} ${height}`} width="100%">
        <Line stroke={colors.border} strokeWidth="1" x1={left} x2={left} y1={top} y2={top + plotHeight} />
        <Line stroke={colors.border} strokeWidth="1" x1={left} x2={left + plotWidth} y1={top + plotHeight} y2={top + plotHeight} />
        {bandTop !== null && bandBottom !== null ? <Rect fill="rgba(201,255,56,0.14)" height={Math.max(1, bandBottom - bandTop)} width={plotWidth} x={left} y={bandTop} /> : null}
        {paths.map((path, index) => <Path d={path} fill="none" key={index} stroke={colors.primary} strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" />)}
        {lastPoint ? <Circle cx={lastX} cy={yPosition(lastPoint.value!, domain.min, domain.max, top, plotHeight)} fill={colors.lime} r="4" /> : null}
      </Svg>
      <View style={{ flexDirection: "row", justifyContent: "space-between" }}>
        <Text style={styles.caption}>{evaluatedAxis ? "M" : "F"}{String(axisStart).padStart(2, "0")}</Text>
        <Text style={styles.caption}>{range ? `좋은 구간 ${formatValue(range.min, range.unit)} ~ ${formatValue(range.max, range.unit)}` : "좋은 구간 미제공"}</Text>
        <Text style={styles.caption}>{evaluatedAxis ? "M" : "F"}{String(axisEnd).padStart(2, "0")}</Text>
      </View>
      <Text style={[styles.caption, { fontSize: 9, textAlign: "center" }]}>{evaluatedAxis ? "M = 측정 가능한 팔꿈치 각도 순번" : "F = 원본 영상 프레임"}</Text>
    </View>
  );
}

function confidenceLabel(level: FeatureAnalysis["confidenceLevel"], assumed = false) {
  if (assumed) return "측정 가능 · 초기 신뢰도 가정";
  if (level === "high") return "신뢰도 높음";
  if (level === "medium") return "일부 구간 경향";
  if (level === "low") return "신뢰도 낮음 · 판단 보류";
  return "분석 제외";
}

function verdictLabel(verdict: FeatureAnalysis["verdict"]) {
  if (verdict === "improve") return "개선 우선";
  if (verdict === "maintain") return "현재 유지";
  if (verdict === "excluded") return "분석 제외";
  return "검토 필요";
}

export function FeatureCard({ feature, onDetails }: { feature: FeatureAnalysis; onDetails: () => void }) {
  const actionAllowed = feature.confidenceLevel === "high" || feature.confidenceLevel === "medium";
  const feedback = actionAllowed && feature.coachingAction ? feature.coachingAction : feature.interpretation || feature.limitation || "해석 문장이 제공되지 않았습니다.";
  const score = featureScore(feature);
  return (
    <Panel style={{ gap: spacing.md, minHeight: 304 }}>
      <View style={{ alignItems: "flex-start", flexDirection: "row", justifyContent: "space-between" }}>
        <View style={{ flex: 1, gap: spacing.xs }}>
          <Text style={styles.eyebrow}>{feature.featureId}</Text>
          <Text style={{ color: colors.primary, fontSize: 17, fontWeight: "700" }}>{feature.label}</Text>
        </View>
        <StatusBadge status={feature.verdict} label={verdictLabel(feature.verdict)} />
      </View>
      <FeatureFrameChart feature={feature} />
      <View style={{ gap: spacing.xs }}>
        <View style={{ alignItems: "flex-end", flexDirection: "row", justifyContent: "space-between" }}>
          <View><Text style={styles.caption}>측정값</Text><Text style={{ color: colors.primary, fontFamily: styles.mono.fontFamily, fontSize: 17, fontWeight: "800" }}>{formatValue(feature.representativeValue, feature.unit)}</Text></View>
          <View style={{ alignItems: "flex-end" }}><Text style={styles.caption}>피처 점수</Text><Text style={{ color: colors.lime, fontFamily: styles.mono.fontFamily, fontSize: 24, fontWeight: "900" }}>{score === null ? "—" : score}<Text style={{ color: colors.muted, fontSize: 10 }}>/100</Text></Text></View>
        </View>
        <Text style={styles.caption}>{featureScoreLabel(feature)}</Text>
      </View>
      <Text style={styles.body}>{feedback}</Text>
      <View style={{ alignItems: "center", flexDirection: "row", justifyContent: "space-between" }}>
        <Text style={{ color: feature.confidenceLevel === "low" || feature.confidenceLevel === "excluded" ? colors.amber : colors.muted, fontSize: 12 }}>
          {confidenceLabel(feature.confidenceLevel, feature.confidenceAssumed)}{feature.confidencePct === null ? "" : ` · ${feature.confidencePct.toFixed(0)}%`}
        </Text>
        <Pressable accessibilityLabel={`${feature.label} 근거 자세히 보기`} accessibilityRole="button" onPress={onDetails} style={{ alignItems: "center", minHeight: 48, justifyContent: "center", paddingHorizontal: spacing.md }}>
          <View style={{ alignItems: "center", borderColor: colors.lime, borderRadius: 12, borderWidth: 1, height: 24, justifyContent: "center", width: 24 }}>
            <Text style={{ color: colors.lime, fontWeight: "900" }}>i</Text>
          </View>
        </Pressable>
      </View>
    </Panel>
  );
}

function signalColor(signal: PostureSignal) {
  if (signal.verdict === "improve") return colors.red;
  if (signal.verdict === "review") return colors.amber;
  return colors.lime;
}

export function PrioritySignals({ signals }: { signals: PostureSignal[] }) {
  if (!signals.length) return null;
  return (
    <Panel style={{ gap: spacing.sm, marginBottom: spacing.lg }}>
      <Text style={styles.eyebrow}>PRIORITY IMPROVEMENTS</Text>
      {signals.slice(0, 3).map((signal, index) => (
        <View key={signal.featureId} style={{ flexDirection: "row", gap: spacing.sm }}>
          <Text style={{ color: signalColor(signal), fontFamily: styles.mono.fontFamily, fontSize: 12, fontWeight: "800" }}>{String(signal.priority ?? index + 1).padStart(2, "0")} ·</Text>
          <Text style={{ color: signalColor(signal), flex: 1, fontSize: 14, fontWeight: "700" }}>{signal.label}{signal.message ? ` · ${signal.message}` : ""}</Text>
        </View>
      ))}
    </Panel>
  );
}

export function PostureSignalRow({ signal }: { signal: PostureSignal }) {
  const range = signal.referenceRange;
  const hasRange = range && range.max > range.min && signal.value !== null;
  let marker = 50;
  let bandLeft = 35;
  let bandWidth = 30;
  if (hasRange) {
    const span = range.max - range.min;
    const domainMin = Math.min(range.min - span, signal.value! - span * 0.2);
    const domainMax = Math.max(range.max + span, signal.value! + span * 0.2);
    const domainSpan = domainMax - domainMin;
    marker = Math.max(0, Math.min(100, ((signal.value! - domainMin) / domainSpan) * 100));
    bandLeft = ((range.min - domainMin) / domainSpan) * 100;
    bandWidth = ((range.max - range.min) / domainSpan) * 100;
  }
  return (
    <View style={{ gap: spacing.sm }}>
      <View style={{ alignItems: "center", flexDirection: "row", gap: spacing.md }}>
        <View style={{ flex: 1, gap: spacing.xs }}>
          <Text style={{ color: colors.primary, fontSize: 14, fontWeight: "700" }}>{signal.label}</Text>
          <Text style={styles.caption}>{range ? `${range.kind === "recommended" ? "좋음" : "참고"} ${formatValue(range.min, range.unit)} ~ ${formatValue(range.max, range.unit)}` : "비교 기준 미제공"}</Text>
        </View>
        <Text style={{ color: signalColor(signal), fontFamily: styles.mono.fontFamily, fontSize: 14, fontWeight: "800" }}>{formatValue(signal.value, signal.unit)}</Text>
      </View>
      <View accessible accessibilityLabel={`${signal.label}, 현재 ${formatValue(signal.value, signal.unit)}`} style={{ backgroundColor: colors.surfaceRaised, height: 10, position: "relative" }}>
        {range ? <View style={{ backgroundColor: "rgba(201,255,56,0.35)", height: "100%", left: `${bandLeft}%`, position: "absolute", width: `${bandWidth}%` }} /> : null}
        <View style={{ backgroundColor: signalColor(signal), borderRadius: 7, height: 18, left: `${marker}%`, marginLeft: -7, marginTop: -4, position: "absolute", width: 14 }} />
      </View>
    </View>
  );
}
