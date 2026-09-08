import React, { useEffect, useMemo, useState } from "react";
import AsyncStorage from "@react-native-async-storage/async-storage";
import Constants from "expo-constants";
import { Pressable, Text, View } from "react-native";
import { useLocalSearchParams, useRouter } from "expo-router";

import { getJob } from "../../src/api";
import { useAuth } from "../../src/auth";
import { AppHeader, Button, ErrorState, LoadingState, Screen, stageLabel } from "../../src/components";
import { ProfileChip } from "../../src/coach-ui";
import type { ActiveAnalysisJob, JobStage } from "../../src/contracts";
import { colors, spacing, styles } from "../../src/theme";

const NOTIFICATION_KEY = "runners-feed.mobile.completion-notifications";
const stages: JobStage[] = ["upload", "queue", "keypoints", "features", "validation", "result"];
const notificationsSupported = Constants.appOwnership !== "expo";

async function getNotifications() {
  if (!notificationsSupported) return null;
  return import("expo-notifications");
}

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
    AsyncStorage.getItem(NOTIFICATION_KEY).then((value) => setNotificationsEnabled(notificationsSupported && value === "true")).catch(() => undefined);
  }, []);

  const toggleNotifications = async () => {
    const next = !notificationsEnabled;
    if (next) {
      const Notifications = await getNotifications();
      if (!Notifications) {
        setError("Expo Go에서는 완료 알림을 사용할 수 없습니다. 개발 APK에서는 정상적으로 사용할 수 있습니다.");
        return;
      }
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
          void getNotifications().then((Notifications) => Notifications?.scheduleNotificationAsync({ content: { title: "러너스 피드 분석 완료", body: "분석 결과를 확인해 보세요." }, trigger: null }));
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
      <AppHeader title="분석하고 있습니다" right={<ProfileChip height={job?.heightCm ? String(job.heightCm) : "—"} onPress={() => router.replace("/")} />} />
      <View style={{ flexDirection: "row", gap: 5, marginBottom: 12 }}>
        <Pressable onPress={() => router.replace("/")} style={{ alignItems: "center", borderColor: colors.border, borderWidth: 1, flex: 1, justifyContent: "center", minHeight: 44 }}><Text style={styles.caption}>대시보드</Text></Pressable>
        <Pressable onPress={() => setMenuOpen((open) => !open)} style={{ alignItems: "center", borderColor: colors.border, borderWidth: 1, flex: 1, justifyContent: "center", minHeight: 44 }}><Text style={styles.caption}>달리기 팁</Text></Pressable>
        <Pressable onPress={() => void toggleNotifications()} style={{ alignItems: "center", borderColor: notificationsEnabled ? colors.lime : colors.border, borderWidth: 1, flex: 1, justifyContent: "center", minHeight: 44 }}><Text style={{ color: notificationsEnabled ? colors.primary : colors.muted, fontSize: 9 }}>완료 알림 {notificationsSupported ? (notificationsEnabled ? "켜짐" : "꺼짐") : "APK 전용"}</Text></Pressable>
      </View>

      {!job && !error ? <LoadingState message="서버에서 분석 상태를 확인하고 있습니다." /> : null}
      {error ? <ErrorState message={error} onRetry={() => router.replace({ pathname: "/progress/[jobId]", params: { jobId } })} /> : null}
      {job ? (
        <>
          <View style={{ alignItems: "center", backgroundColor: colors.surfaceSecondary, borderColor: colors.border, borderWidth: 1, flexDirection: "row", gap: 14, minHeight: 136, padding: 14 }}>
            <View style={{ alignItems: "center", borderColor: colors.border, borderRadius: 42, borderTopColor: failed ? colors.red : colors.lime, borderWidth: 7, height: 82, justifyContent: "center", width: 82 }}><Text style={{ color: failed ? colors.red : colors.primary, fontFamily: styles.mono.fontFamily, fontSize: 16, fontWeight: "900" }}>{job.progressPct === null ? "—" : `${Math.round(job.progressPct)}%`}</Text></View>
            <View style={{ flex: 1 }}><Text style={styles.eyebrow}>현재 단계 · {Math.min(activeIndex + 1, 4).toString().padStart(2, "0")}/04</Text><Text style={{ color: colors.primary, fontSize: 16, fontWeight: "900", lineHeight: 22, marginTop: 8 }}>{failed ? "분석을 완료하지 못했습니다" : stageLabel(job.stage)}</Text><Text style={[styles.caption, { marginTop: 7 }]}>{failed ? job.error ?? "다른 영상으로 다시 시도해 주세요." : job.estimatedCompletionSeconds !== null ? `완료까지 약 ${job.estimatedCompletionSeconds}초` : "분석은 계속 진행됩니다."}</Text></View>
          </View>

          <View style={{ borderColor: colors.border, borderWidth: 1, flexDirection: "row", marginTop: 8 }}>
            {[{ label: "업로드", threshold: 0 }, { label: "관절 추출", threshold: 2 }, { label: "특성값", threshold: 3 }, { label: "검증", threshold: 4 }].map((item, index) => { const active = activeIndex >= item.threshold; return <View key={item.label} style={{ alignItems: "center", backgroundColor: activeIndex === item.threshold ? "rgba(201,255,56,0.05)" : colors.background, borderRightColor: colors.border, borderRightWidth: index < 3 ? 1 : 0, flex: 1, justifyContent: "center", minHeight: 48 }}><Text style={{ color: active ? colors.lime : colors.muted, fontSize: 9 }}>{item.label}</Text></View>; })}
          </View>

          {menuOpen ? <View style={{ backgroundColor: colors.surface, borderColor: colors.border, borderWidth: 1, marginTop: 10, padding: 15 }}><Text style={styles.eyebrow}>RUNNING TIP</Text><Text style={{ color: colors.primary, fontSize: 13, fontWeight: "800", lineHeight: 20, marginTop: 9 }}>상체에 힘을 빼고 자연스러운 시선을 유지해 보세요.</Text><Text style={[styles.caption, { marginTop: 7 }]}>분석 완료 후 내 측정값에 맞는 피드백으로 바뀝니다.</Text></View> : null}

          <View style={{ backgroundColor: colors.surface, borderColor: colors.border, borderWidth: 1, marginTop: 14, minHeight: 210, padding: 20 }}><Text style={styles.eyebrow}>RUNNERS FEED METHOD</Text><Text style={{ color: colors.primary, fontSize: 21, fontWeight: "900", lineHeight: 27, marginTop: 13 }}>측정에서 피드백까지{`\n`}근거를 연결합니다</Text><View style={{ alignItems: "center", flexDirection: "row", justifyContent: "space-between", marginTop: 22 }}>{["관절 측정", "기준 비교", "피드백 검증"].map((label, index) => <React.Fragment key={label}><View style={{ alignItems: "center", borderColor: colors.border, borderWidth: 1, flex: 1, justifyContent: "center", minHeight: 44 }}><Text style={{ color: colors.secondary, fontSize: 9 }}>{label}</Text></View>{index < 2 ? <Text style={{ color: colors.lime, marginHorizontal: 5 }}>→</Text> : null}</React.Fragment>)}</View></View>
          {failed ? <Button label="영상 다시 선택" onPress={() => router.replace("/upload")} style={{ marginTop: 10 }} /> : null}
        </>
      ) : null}
    </Screen>
  );
}
