import React, { useEffect, useMemo, useState } from "react";
import { Text, View } from "react-native";
import { useLocalSearchParams, useRouter } from "expo-router";

import { getJob } from "../../src/api";
import { useAuth } from "../../src/auth";
import { AppHeader, Button, ErrorState, LoadingState, Panel, ProgressBar, Screen, stageLabel } from "../../src/components";
import type { ActiveAnalysisJob, JobStage } from "../../src/contracts";
import { colors, spacing, styles } from "../../src/theme";

const stages: JobStage[] = ["queue", "keypoints", "features", "validation", "result"];

export default function ProgressScreen() {
  const { jobId: rawJobId } = useLocalSearchParams<{ jobId: string }>();
  const jobId = Array.isArray(rawJobId) ? rawJobId[0] : rawJobId;
  const router = useRouter();
  const { token } = useAuth();
  const [job, setJob] = useState<ActiveAnalysisJob | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!token || !jobId) return;
    let mounted = true;
    let timer: ReturnType<typeof setInterval> | undefined;
    const poll = async () => {
      try {
        const next = await getJob(token, jobId);
        if (!mounted) return;
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
  }, [token, jobId, router]);

  const activeIndex = useMemo(() => (job ? Math.max(0, stages.indexOf(job.stage)) : 0), [job]);

  return (
    <Screen>
      <AppHeader eyebrow="ANALYSIS IN PROGRESS" title="분석 중" />
      {!job && !error ? <LoadingState message="서버에서 분석 상태를 확인하고 있습니다." /> : null}
      {error ? <ErrorState message={error} onRetry={() => router.replace({ pathname: "/progress/[jobId]", params: { jobId } })} /> : null}
      {job ? (
        <>
          <Panel style={{ gap: spacing.lg, marginBottom: spacing.lg }}>
            <View style={{ alignItems: "center", flexDirection: "row", justifyContent: "space-between" }}>
              <Text style={styles.eyebrow}>JOB STATUS</Text>
              <Text style={{ color: job.status === "FAILED" ? colors.red : colors.lime, fontFamily: styles.mono.fontFamily }}>{job.progressPct === null ? "—" : `${Math.round(job.progressPct)}%`}</Text>
            </View>
            <Text style={{ color: colors.primary, fontSize: 24, fontWeight: "800" }}>{stageLabel(job.stage)}</Text>
            <ProgressBar value={job.progressPct} />
            <Text style={styles.body}>{job.status === "FAILED" ? job.error ?? "분석에 실패했습니다." : "분석이 끝나면 결과 화면으로 이동합니다. 앱을 닫아도 분석은 계속 진행됩니다."}</Text>
          </Panel>
          <Panel style={{ gap: spacing.md, marginBottom: spacing.lg }}>
            {stages.map((stage, index) => {
              const complete = job.status === "SUCCESS" || index < activeIndex;
              const current = stage === job.stage;
              return (
                <View key={stage} style={{ alignItems: "center", flexDirection: "row", gap: spacing.md }}>
                  <View style={{ alignItems: "center", backgroundColor: complete || current ? colors.lime : colors.surfaceRaised, borderColor: complete || current ? colors.lime : colors.border, borderRadius: 12, borderWidth: 1, height: 24, justifyContent: "center", width: 24 }}>
                    <Text style={{ color: complete || current ? colors.limeInk : colors.muted, fontSize: 11, fontWeight: "800" }}>{complete ? "✓" : index + 1}</Text>
                  </View>
                  <Text style={{ color: current ? colors.primary : colors.secondary, fontSize: 15, fontWeight: current ? "700" : "500" }}>{stageLabel(stage)}</Text>
                </View>
              );
            })}
          </Panel>
          {job.status === "FAILED" || job.status === "ERROR" ? <Button label="대시보드로 돌아가기" onPress={() => router.replace("/")} kind="secondary" /> : <Button label="대시보드에서 계속 보기" onPress={() => router.replace("/")} kind="secondary" />}
        </>
      ) : null}
    </Screen>
  );
}
