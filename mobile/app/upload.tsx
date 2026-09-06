import React, { useEffect, useState } from "react";
import { Image, Text, View } from "react-native";
import * as ImagePicker from "expo-image-picker";
import { useRouter } from "expo-router";

import { uploadVideo, updateProfile } from "../src/api";
import { useAuth } from "../src/auth";
import { AppHeader, Button, ErrorState, Panel, Screen, TextField } from "../src/components";
import { colors, spacing, styles } from "../src/theme";

type SelectedVideo = { uri: string; name: string; mimeType: string; duration?: number | null; size?: number | null };

function videoFromAsset(asset: ImagePicker.ImagePickerAsset): SelectedVideo {
  const fallbackName = asset.uri.split("/").pop() || `running-${Date.now()}.mp4`;
  const name = asset.fileName || fallbackName;
  const lower = name.toLowerCase();
  const mimeType = asset.mimeType || (lower.endsWith(".mov") ? "video/quicktime" : "video/mp4");
  return { uri: asset.uri, name, mimeType, duration: asset.duration, size: asset.fileSize };
}

export default function UploadScreen() {
  const router = useRouter();
  const { token, profile, refreshProfile } = useAuth();
  const [height, setHeight] = useState(profile?.heightCm ? String(profile.heightCm) : "");
  const [video, setVideo] = useState<SelectedVideo | null>(null);
  const [progress, setProgress] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (profile?.heightCm && !height) setHeight(String(profile.heightCm));
  }, [profile?.heightCm, height]);

  const selectVideo = async (camera: boolean) => {
    setError(null);
    const permission = camera
      ? await ImagePicker.requestCameraPermissionsAsync()
      : await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (!permission.granted) {
      setError(`${camera ? "카메라" : "사진 보관함"} 권한이 필요합니다.`);
      return;
    }
    const result = camera
      ? await ImagePicker.launchCameraAsync({ mediaTypes: ["videos"], videoMaxDuration: 60 })
      : await ImagePicker.launchImageLibraryAsync({ mediaTypes: ["videos"], selectionLimit: 1 });
    if (result.canceled || !result.assets[0]) return;
    const selected = videoFromAsset(result.assets[0]);
    if (!selected.name.toLowerCase().endsWith(".mp4") && !selected.name.toLowerCase().endsWith(".mov")) {
      setError("MP4 또는 MOV 영상만 선택할 수 있습니다.");
      return;
    }
    setVideo(selected);
  };

  const start = async () => {
    if (!token || !video) return;
    const numericHeight = Number(height);
    if (!Number.isFinite(numericHeight) || numericHeight < 50 || numericHeight > 250) {
      setError("분석 대상 키를 50~250cm 범위로 입력해 주세요.");
      return;
    }
    setBusy(true);
    setError(null);
    setProgress(0);
    try {
      if (profile?.heightCm !== numericHeight) {
        await updateProfile(token, numericHeight);
        await refreshProfile();
      }
      const job = await uploadVideo(token, video, numericHeight, setProgress);
      router.replace({ pathname: "/progress/[jobId]", params: { jobId: job.jobId } });
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "영상 분석을 시작하지 못했습니다.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Screen>
      <AppHeader eyebrow="NEW ANALYSIS" title="러닝 영상 분석" />
      <Panel style={{ gap: spacing.md, marginBottom: spacing.lg }}>
        <Text style={{ color: colors.primary, fontSize: 18, fontWeight: "700" }}>촬영 조건</Text>
        <Text style={styles.body}>전신이 보이고 카메라가 옆에 있는 영상을 선택해 주세요. 분석 결과는 촬영 각도와 가림의 영향을 받습니다.</Text>
        <View style={{ gap: spacing.sm }}>
          <Text style={styles.caption}>최소 조건</Text>
          <Text style={styles.body}>01  전신이 프레임 안에 있어야 합니다.</Text>
          <Text style={styles.body}>02  10초 이상, MP4 또는 MOV 형식이어야 합니다.</Text>
          <Text style={styles.body}>03  움직임이 심하게 흔들리지 않아야 합니다.</Text>
        </View>
      </Panel>
      <View style={{ flexDirection: "row", gap: spacing.sm, marginBottom: spacing.lg }}>
        <Button label="갤러리에서 선택" onPress={() => void selectVideo(false)} kind="secondary" style={{ flex: 1 }} />
        <Button label="카메라로 촬영" onPress={() => void selectVideo(true)} kind="secondary" style={{ flex: 1 }} />
      </View>
      {video ? (
        <Panel style={{ gap: spacing.md, marginBottom: spacing.lg }}>
          <Text style={styles.eyebrow}>SELECTED VIDEO</Text>
          <View style={{ backgroundColor: colors.surfaceSecondary, height: 160, overflow: "hidden" }}>
            <Image source={{ uri: video.uri }} style={{ height: "100%", width: "100%" }} resizeMode="cover" />
          </View>
          <Text style={{ color: colors.primary, fontWeight: "700" }}>{video.name}</Text>
          <Text style={styles.caption}>{video.duration ? `${Math.round(video.duration / 1000)}초` : "길이 확인 중"}{video.size ? ` · ${(video.size / 1024 / 1024).toFixed(1)}MB` : ""}</Text>
        </Panel>
      ) : null}
      <Panel style={{ gap: spacing.md }}>
        <TextField keyboardType="decimal-pad" label="분석 대상 키 (cm)" onChangeText={setHeight} placeholder="예: 175" value={height} />
        <Text style={styles.caption}>프로필 키와 다르면 이번 분석에만 적용할 수 있습니다.</Text>
        <Button label={busy ? `업로드 중 ${Math.round(progress * 100)}%` : "분석 시작"} onPress={() => void start()} disabled={!video} loading={busy} />
        {busy ? <View style={{ backgroundColor: colors.surfaceRaised, height: 6, overflow: "hidden" }}><View style={{ backgroundColor: colors.lime, height: "100%", width: `${Math.max(2, progress * 100)}%` }} /></View> : null}
      </Panel>
      {error ? <View style={{ marginTop: spacing.lg }}><ErrorState message={error} /></View> : null}
    </Screen>
  );
}
