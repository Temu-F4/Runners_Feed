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

import type { ActiveAnalysisJob, FeatureAnalysis, JobStage } from "./contracts";
import { colors, formatDate, formatValue, spacing, styles } from "./theme";

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
    <View style={{ paddingTop: spacing.xxl, paddingBottom: spacing.xxl }}>
      <View style={{ alignItems: "center", flexDirection: "row", justifyContent: "space-between" }}>
        <View style={{ flex: 1, gap: spacing.sm }}>
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
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ disabled: disabled || loading }}
      disabled={disabled || loading}
      onPress={onPress}
      style={({ pressed }) => [
        styles.button,
        kind === "primary" ? styles.primaryButton : styles.secondaryButton,
        (disabled || loading) && { opacity: 0.45 },
        pressed && !disabled && !loading && { opacity: 0.75 },
        style,
      ]}
    >
      {loading ? <ActivityIndicator color={kind === "primary" ? colors.limeInk : colors.lime} /> : <Text style={[styles.buttonText, { color: kind === "primary" ? colors.limeInk : colors.primary }]}>{label}</Text>}
    </Pressable>
  );
}

export function TextField({ label, error, ...props }: TextInputProps & { label: string; error?: string }) {
  return (
    <View style={{ gap: spacing.sm }}>
      <Text style={styles.caption}>{label}</Text>
      <TextInput
        {...props}
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
  const isDanger = status === "FAILED" || status === "ERROR";
  const isActive = status === "PROCESSING" || status === "QUEUED";
  return (
    <View style={{ alignSelf: "flex-start", backgroundColor: isDanger ? "#3a1e1a" : isActive ? "#26320e" : colors.surfaceRaised, borderColor: isDanger ? colors.red : isActive ? colors.lime : colors.border, borderRadius: 2, borderWidth: 1, paddingHorizontal: spacing.sm, paddingVertical: 6 }}>
      <Text style={{ color: isDanger ? colors.red : isActive ? colors.lime : colors.secondary, fontFamily: styles.mono.fontFamily, fontSize: 11, fontWeight: "700" }}>{label ?? status}</Text>
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
  upload: "영상 업로드",
  queue: "분석 대기",
  keypoints: "자세 추적",
  features: "지표 계산",
  validation: "결과 검증",
  result: "결과 준비",
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

export function JobCard({ job, onPress }: { job: ActiveAnalysisJob; onPress: () => void }) {
  const statusLabel = job.status === "SUCCESS" ? "완료" : job.status === "FAILED" ? "실패" : job.status === "PROCESSING" ? "분석 중" : "대기 중";
  return (
    <Pressable onPress={onPress} style={({ pressed }) => [styles.panel, { gap: spacing.md, opacity: pressed ? 0.75 : 1 }]}>
      <View style={{ alignItems: "center", flexDirection: "row", justifyContent: "space-between" }}>
        <View style={{ flex: 1, gap: spacing.xs }}>
          <Text style={{ color: colors.primary, fontSize: 16, fontWeight: "700" }}>{job.title}</Text>
          <Text style={styles.caption}>{formatDate(job.createdAt)}</Text>
        </View>
        <StatusBadge status={job.status} label={statusLabel} />
      </View>
      <View style={{ gap: spacing.sm }}>
        <View style={{ alignItems: "center", flexDirection: "row", justifyContent: "space-between" }}>
          <Text style={styles.caption}>{stageLabel(job.stage)}</Text>
          <Text style={styles.mono}>{job.progressPct === null ? "—" : `${Math.round(job.progressPct)}%`}</Text>
        </View>
        <ProgressBar value={job.progressPct} />
      </View>
    </Pressable>
  );
}

export function BottomNavigation() {
  const pathname = usePathname();
  const router = useRouter();
  const items = [
    { label: "대시보드", path: "/" as const },
    { label: "분석", path: "/upload" as const },
    { label: "기록", path: "/history" as const },
  ];
  return (
    <View style={{ backgroundColor: colors.surface, borderColor: colors.border, borderTopWidth: 1, bottom: 0, flexDirection: "row", left: 0, paddingBottom: spacing.lg, paddingTop: spacing.sm, position: "absolute", right: 0 }}>
      {items.map((item) => {
        const active = item.path === "/" ? pathname === "/" : pathname.startsWith(item.path);
        return (
          <Pressable key={item.path} onPress={() => router.push(item.path)} style={{ alignItems: "center", flex: 1, gap: spacing.xs, minHeight: 48, justifyContent: "center" }}>
            <View style={{ backgroundColor: active ? colors.lime : colors.border, borderRadius: 5, height: 5, width: 5 }} />
            <Text style={{ color: active ? colors.lime : colors.muted, fontSize: 12, fontWeight: active ? "800" : "500" }}>{item.label}</Text>
          </Pressable>
        );
      })}
    </View>
  );
}

export function RangeBar({ feature }: { feature: FeatureAnalysis }) {
  const range = feature.referenceRange;
  if (!range || feature.representativeValue === null || range.max <= range.min) {
    return <EmptyState title="기준 범위 없음" message="이 지표에는 현재 비교 가능한 기준 범위가 제공되지 않았습니다." />;
  }
  const position = Math.max(0, Math.min(100, ((feature.representativeValue - range.min) / (range.max - range.min)) * 100));
  return (
    <View style={{ gap: spacing.sm }}>
      <View style={{ backgroundColor: "#334313", borderRadius: 2, height: 12, position: "relative" }}>
        <View style={{ backgroundColor: colors.lime, borderRadius: 6, height: 20, left: `${position}%`, marginLeft: -10, marginTop: -4, position: "absolute", width: 20 }} />
      </View>
      <View style={{ flexDirection: "row", justifyContent: "space-between" }}>
        <Text style={styles.caption}>{formatValue(range.min, range.unit)}</Text>
        <Text style={styles.caption}>{formatValue(range.max, range.unit)}</Text>
      </View>
    </View>
  );
}

export function FeatureCard({ feature, onDetails }: { feature: FeatureAnalysis; onDetails: () => void }) {
  const confidence = feature.confidenceLevel === "excluded" || feature.confidenceLevel === "low" ? "판단 보류" : feature.confidenceLevel === "medium" ? "일부 구간 경향" : "신뢰도 높음";
  const verdictLabel = feature.verdict === "improve" ? "개선 우선" : feature.verdict === "maintain" ? "현재 유지" : feature.verdict === "excluded" ? "분석 제외" : "검토 필요";
  return (
    <Panel style={{ gap: spacing.md }}>
      <View style={{ alignItems: "flex-start", flexDirection: "row", justifyContent: "space-between" }}>
        <View style={{ flex: 1, gap: spacing.xs }}>
          <Text style={styles.eyebrow}>{feature.featureId}</Text>
          <Text style={{ color: colors.primary, fontSize: 17, fontWeight: "700" }}>{feature.label}</Text>
        </View>
        <StatusBadge status={feature.verdict} label={verdictLabel} />
      </View>
      <Text style={{ color: colors.lime, fontFamily: styles.mono.fontFamily, fontSize: 26, fontWeight: "700" }}>{formatValue(feature.representativeValue, feature.unit)}</Text>
      <RangeBar feature={feature} />
      <Text style={styles.body}>{feature.interpretation || feature.limitation}</Text>
      <View style={{ alignItems: "center", flexDirection: "row", justifyContent: "space-between" }}>
        <Text style={{ color: feature.confidenceLevel === "low" || feature.confidenceLevel === "excluded" ? colors.amber : colors.muted, fontSize: 12 }}>{confidence}</Text>
        <Pressable accessibilityRole="button" onPress={onDetails} style={{ alignItems: "center", minHeight: 48, justifyContent: "center", paddingHorizontal: spacing.md }}>
          <Text style={{ color: colors.lime, fontSize: 13, fontWeight: "800" }}>근거 보기</Text>
        </Pressable>
      </View>
    </Panel>
  );
}
