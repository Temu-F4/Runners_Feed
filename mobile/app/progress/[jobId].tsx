import React, { useEffect, useMemo, useState } from "react";
import AsyncStorage from "@react-native-async-storage/async-storage";
import * as Notifications from "expo-notifications";
import { Text, View } from "react-native";
import { useLocalSearchParams, useRouter } from "expo-router";

import { getJob } from "../../src/api";
import { useAuth } from "../../src/auth";
import { AppHeader, Button, ErrorState, LoadingState, Panel, ProgressBar, Screen, stageLabel } from "../../src/components";
import type { ActiveAnalysisJob, JobStage } from "../../src/contracts";
import { colors, spacing, styles } from "../../src/theme";

const NOTIFICATION_KEY = "runners-feed.mobile.completion-notifications";
const stages: JobStage[] = ["upload", "queue", "keypoints", "features", "validation", "result"];

export default function ProgressScreen() {
  const { jobId: rawJobId } = useLocalSearchParams<{ jobId: string }>();
  const jobId = Array.isArray(rawJobId) ? rawJobId[0] : rawJobId;
  const router = useRouter();
  const { token } = useAuth();
  const [job, setJob] = useState<ActiveAnalysisJob | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [menuOpen, setMenuOpen] = useState(false);
  const [notificationsEnabled, setNotificationsEnabled] = useState(false);

  useEffect(() => {
    AsyncStorage.getItem(NOTIFICATION_KEY).then((value) => setNotificationsEnabled(value === "true")).catch(() => undefined);
  }, []);

  const toggleNotifications = async () => {
    const next = !notificationsEnabled;
    if (next) {
      const permission = await Notifications.requestPermissionsAsync();
      if (!permission.granted) {
        setError("완료 알림을 사용하려면 알림 권한이 필요합니다.");
        return;
      }
    }
    setNotificationsEnabled(next);
    await AsyncStorage.setItem(NOTIFICATION_KEY, String(next));
  };

  useEffect(() => {
    if (!token || !jobId) return;
    let mounted = true;
    let timer: ReturnType<typeof setInterval> | undefined;
    let previousStatus: ActiveAnalysisJob["status"] | null = null;
    const poll = async () => {
      try {
        const next = await getJob(token, jobId);
        if (!mounted) return;
        if (previousStatus !== "SUCCESS" && next.status === "SUCCESS" && notificationsEnabled) {
          void Notifications.scheduleNotificationAsync({ content: { title: "러너스 피드 분석 완료", body: "분석 결과를 확인해 보세요." }, trigger: null });
        }
        previousStatus = next.status;
        setJob(next);
        if (next.status === "SUCCESS") {
          router.replace({ pathname: "/result/[jobId]", params: { jobId } });
        } else if (next.status === "FAILED" || next.status === "ERROR") {
          if (timer) clearInterval(timer);
        }
      } catch (cause) {
        if (mounted) setError(cause instanceof Error ? cause.message : "분석 상태를 불러오지 못했습니다.");
      }
    };
    void poll();
    timer = setInterval(() => void poll(), 3000);
    return () => {
      mounted = false;
      if (timer) clearInterval(timer);
    };
  }, [token, jobId, router, notificationsEnabled]);

  const activeIndex = useMemo(() => (job ? Math.max(0, stages.indexOf(job.stage)) : 0), [job]);
  const failed = job?.status === "FAILED" || job?.status === "ERROR";

  return (
    <Screen>
      <View style={{ position: "relative" }}>
        <AppHeader
          eyebrow="ANALYSIS IN PROGRESS"
          title="분석 중"
          right={<Button label="••" kind="secondary" onPress={() => setMenuOpen((open) => !open)} style={{ minHeight: 48, paddingHorizontal: spacing.md }} />}
        />
        {menuOpen ? (
          <Panel style={{ gap: spacing.sm, marginBottom: spacing.lg }}>
            <Button label="대시보드" kind="secondary" onPress={() => router.replace("/")} />
            <Button label="달리기 팁" kind="secondary" onPress={() => setMenuOpen(false)} />
            <View style={{ alignItems: "center", flexDirection: "row", justifyContent: "space-between", minHeight: 48 }}>
              <Text style={styles.body}>완료 알림</Text>
              <Button label={notificationsEnabled ? "켜짐" : "꺼짐"} kind={notificationsEnabled ? "primary" : "secondary"} onPress={() => void toggleNotifications()} style={{ minHeight: 44, paddingHorizontal: spacing.md }} />
            </View>
          </Panel>
        ) : null}
      </View>

      {!job && !error ? <LoadingState message="서버에서 분석 상태를 확인하고 있습니다." /> : null}
      {error ? <ErrorState message={error} onRetry={() => router.replace({ pathname: "/progress/[jobId]", params: { jobId } })} /> : null}
      {job ? (
        <>
          <Panel style={{ gap: spacing.lg, marginBottom: spacing.lg }}>
            <View style={{ alignItems: "center", flexDirection: "row", justifyContent: "space-between" }}>
              <Text style={styles.eyebrow}>JOB STATUS</Text>
              <Text style={{ color: failed ? colors.red : colors.lime, fontFamily: styles.mono.fontFamily }}>{job.progressPct === null ? "—" : `${Math.round(job.progressPct)}%`}</Text>
            </View>
            <Text style={{ color: colors.primary, fontSize: 24, fontWeight: "800" }}>{failed ? "분석을 완료하지 못했습니다" : stageLabel(job.stage)}</Text>
            <ProgressBar value={job.progressPct} />
            <Text style={styles.body}>{failed ? job.error ?? "분석에 실패했습니다. 다른 영상으로 다시 시도해 주세요." : job.estimatedCompletionSeconds !== null ? `약 ${Math.ceil(job.estimatedCompletionSeconds / 60)}분 후 완료 예정입니다.` : "분석이 끝나면 결과 화면으로 이동합니다. 앱을 닫아도 분석은 계속 진행됩니다."}</Text>
          </Panel>

          <Panel style={{ gap: spacing.md, marginBottom: spacing.lg }}>
            <Text style={styles.eyebrow}>PROCESS STAGES</Text>
            {stages.map((stage, index) => {
              const complete = job.status === "SUCCESS" || index < activeIndex;
              const current = stage === job.stage;
              const danger = failed && current;
              return (
                <View key={stage} style={{ alignItems: "center", flexDirection: "row", gap: spacing.md, minHeight: 48 }}>
                  <View style={{ alignItems: "center", backgroundColor: danger ? colors.red : complete || current ? colors.lime : colors.surfaceRaised, borderColor: danger ? colors.red : complete || current ? colors.lime : colors.border, borderRadius: 12, borderWidth: 1, height: 24, justifyContent: "center", width: 24 }}>
                    <Text style={{ color: danger ? colors.primary : complete || current ? colors.limeInk : colors.muted, fontSize: 11, fontWeight: "800" }}>{danger ? "!" : complete ? "✓" : index + 1}</Text>
                  </View>
                  <Text style={{ color: danger ? colors.red : current ? colors.primary : colors.secondary, flex: 1, fontSize: 15, fontWeight: current ? "700" : "500" }}>{stageLabel(stage)}</Text>
                  <Text style={styles.caption}>{danger ? "실패" : complete ? "완료" : current ? "진행 중" : "대기"}</Text>
                </View>
              );
            })}
          </Panel>

          <Panel style={{ gap: spacing.md, marginBottom: spacing.lg }}>
            <Text style={styles.eyebrow}>WHY RUNNERS FEED</Text>
            <Text style={{ color: colors.primary, fontSize: 17, fontWeight: "700" }}>근거를 확인하는 분석</Text>
            <View style={{ alignItems: "center", flexDirection: "row", justifyContent: "space-between" }}>
              {["관절 측정", "기준 비교", "피드백 검증"].map((label, index) => <React.Fragment key={label}><Text style={styles.caption}>{label}</Text>{index < 2 ? <Text style={{ color: colors.lime }}>→</Text> : null}</React.Fragment>)}
            </View>
            <Text style={styles.body}>측정값과 기준을 확인한 뒤 검증된 정보만 결과에 표시합니다.</Text>
          </Panel>

          <Panel style={{ gap: spacing.sm, marginBottom: spacing.lg }}>
            <Text style={styles.eyebrow}>RUNNING TIP · 01</Text>
            <Text style={styles.body}>다음 러닝에서는 시선을 10m 앞에 두고 상체의 긴장을 풀어 보세요.</Text>
            <Text style={styles.caption}>분석이 끝나면 내 측정값에 맞춘 팁으로 바뀝니다.</Text>
          </Panel>
          <Button label="대시보드로 돌아가기" onPress={() => router.replace("/")} kind="secondary" />
        </>
      ) : null}
    </Screen>
  );
}
