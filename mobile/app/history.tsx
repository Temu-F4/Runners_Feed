import React, { useCallback, useEffect, useState } from "react";
import { RefreshControl, Text } from "react-native";
import { useFocusEffect, useRouter } from "expo-router";

import { listJobs } from "../src/api";
import { useAuth } from "../src/auth";
import { AppHeader, EmptyState, ErrorState, JobCard, LoadingState, Screen } from "../src/components";
import type { ActiveAnalysisJob } from "../src/contracts";
import { colors, spacing, styles } from "../src/theme";

export default function HistoryScreen() {
  const router = useRouter();
  const { token } = useAuth();
  const [jobs, setJobs] = useState<ActiveAnalysisJob[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (refresh = false) => {
    if (!token) return;
    if (refresh) setRefreshing(true);
    else setLoading(true);
    setError(null);
    try {
      setJobs((await listJobs(token)).jobs);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "분석 기록을 불러오지 못했습니다.");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [token]);

  useEffect(() => { if (token) void load(); }, [token, load]);
  useFocusEffect(useCallback(() => { if (token) void load(true); return undefined; }, [token, load]));

  const openJob = (job: ActiveAnalysisJob) => {
    if (job.status === "SUCCESS") router.push({ pathname: "/result/[jobId]", params: { jobId: job.jobId } });
    else router.push({ pathname: "/progress/[jobId]", params: { jobId: job.jobId } });
  };

  return (
    <Screen refreshControl={<RefreshControl onRefresh={() => void load(true)} refreshing={refreshing} tintColor={colors.lime} />}>
      <AppHeader eyebrow="RUN HISTORY" title="분석 기록" />
      <Text style={[styles.caption, { marginBottom: spacing.lg }]}>이 기기에서 생성한 분석 기록입니다. Kakao 로그인하면 계정과 함께 보존됩니다.</Text>
      {loading ? <LoadingState message="기록을 불러오는 중입니다." /> : null}
      {error ? <ErrorState message={error} onRetry={() => void load()} /> : null}
      {!loading && !error && jobs.length === 0 ? <EmptyState title="아직 분석 기록이 없습니다" message="첫 러닝 영상을 업로드하면 이곳에서 결과를 다시 볼 수 있습니다." /> : null}
      {jobs.map((job) => <JobCard key={job.jobId} job={job} onPress={() => openJob(job)} />)}
    </Screen>
  );
}
