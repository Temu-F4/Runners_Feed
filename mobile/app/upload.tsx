import React, { useEffect, useState } from "react";
import { ImagePickerAsset, launchCameraAsync, launchImageLibraryAsync, requestCameraPermissionsAsync, requestMediaLibraryPermissionsAsync } from "expo-image-picker";
import { Text, View } from "react-native";
import { useRouter } from "expo-router";

import { uploadVideo } from "../src/api";
import { useAuth } from "../src/auth";
import { AppHeader, Button, ErrorState, Panel, Screen, TextField } from "../src/components";
import { colors, spacing, styles } from "../src/theme";

const MAX_VIDEO_BYTES = 250 * 1024 * 1024;
const MIN_VIDEO_MS = 3_000;
const MAX_VIDEO_MS = 10_000;

type UploadValidation = "idle" | "valid" | "invalid_type" | "too_large" | "too_short" | "too_long" | "unreadable";
type SelectedVideo = { uri: string; name: string; mimeType: string; duration?: number | null; size?: number | null; validation: UploadValidation };

function videoFromAsset(asset: ImagePickerAsset): SelectedVideo {
  const fallbackName = asset.uri.split("/").pop() || `running-${Date.now()}.mp4`;
  const name = asset.fileName || fallbackName;
  const lower = name.toLowerCase();
  const mimeType = asset.mimeType || (lower.endsWith(".mp4") ? "video/mp4" : "video/quicktime");
  let validation: UploadValidation = "valid";
  if (!lower.endsWith(".mp4") || mimeType !== "video/mp4") validation = "invalid_type";
  else if (asset.fileSize !== null && asset.fileSize !== undefined && asset.fileSize > MAX_VIDEO_BYTES) validation = "too_large";
  else if (asset.duration !== null && asset.duration !== undefined && asset.duration < MIN_VIDEO_MS) validation = "too_short";
  else if (asset.duration !== null && asset.duration !== undefined && asset.duration > MAX_VIDEO_MS) validation = "too_long";
  return { uri: asset.uri, name, mimeType, duration: asset.duration, size: asset.fileSize, validation };
}

function validationMessage(validation: UploadValidation) {
  if (validation === "invalid_type") return "MP4 영상만 선택할 수 있습니다. 다른 파일을 선택해 주세요.";
  if (validation === "too_large") return "영상은 250MiB 이하만 업로드할 수 있습니다.";
  if (validation === "too_short") return "분석 영상은 3초 이상이어야 합니다.";
  if (validation === "too_long") return "분석 영상은 10초 이하이어야 합니다.";
  if (validation === "unreadable") return "영상을 읽을 수 없습니다. 다른 영상을 선택해 주세요.";
  return null;
}

export default function UploadScreen() {
  const router = useRouter();
  const { token, profile } = useAuth();
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
    const permission = camera ? await requestCameraPermissionsAsync() : await requestMediaLibraryPermissionsAsync();
    if (!permission.granted) {
      setError(`${camera ? "카메라" : "사진 보관함"} 권한이 필요합니다.`);
      return;
    }
    const result = camera
      ? await launchCameraAsync({ mediaTypes: ["videos"], videoMaxDuration: 10, quality: 1 })
      : await launchImageLibraryAsync({ mediaTypes: ["videos"], selectionLimit: 1 });
    if (result.canceled || !result.assets[0]) return;
    setVideo(videoFromAsset(result.assets[0]));
  };

  const start = async () => {
    if (!token || !video) return;
    const validationMessageText = validationMessage(video.validation);
    if (validationMessageText) {
      setError(validationMessageText);
      return;
    }
    const numericHeight = Number(height);
    if (!Number.isFinite(numericHeight) || numericHeight < 50 || numericHeight > 250) {
      setError("분석 대상 키를 50~250cm 범위로 입력해 주세요.");
      return;
    }
    setBusy(true);
    setError(null);
    setProgress(0);
    try {
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
      <AppHeader eyebrow="NEW ANALYSIS" title="분석할 영상을 선택하세요" />
      <Text style={[styles.body, { marginBottom: spacing.lg }]}>측면에서 전신이 보이는 짧은 영상이면 측정이 더 안정적입니다.</Text>

      <Panel style={{ gap: spacing.md, marginBottom: spacing.lg }}>
        <View accessible accessibilityLabel="측면에서 달리는 사람의 전신이 모두 보이는 샘플 촬영 이미지 자리" style={{ alignItems: "center", backgroundColor: colors.surfaceSecondary, borderColor: colors.border, borderWidth: 1, height: 156, justifyContent: "center" }}>
          <Text style={styles.eyebrow}>CAPTURE GUIDE IMAGE</Text>
          <Text style={{ color: colors.secondary, fontSize: 17, fontWeight: "700", marginTop: spacing.sm }}>측면 · 전신 · 흔들림 없이</Text>
          <Text style={[styles.caption, { marginTop: spacing.sm }]}>승인된 촬영 가이드 이미지가 준비되면 이 영역에 표시됩니다.</Text>
        </View>
        <View style={{ flexDirection: "row" }}>
          {["카메라는 옆쪽에", "머리부터 발까지 한 화면에", "3–10초 흔들림 없이"].map((item, index) => (
            <View key={item} style={{ borderColor: colors.border, borderRightWidth: index < 2 ? 1 : 0, flex: 1, gap: spacing.sm, minHeight: 90, paddingHorizontal: spacing.sm }}>
              <Text style={styles.eyebrow}>0{index + 1}</Text>
              <Text style={{ color: colors.primary, fontSize: 13, fontWeight: "700" }}>{item}</Text>
            </View>
          ))}
        </View>
      </Panel>

      <View style={{ flexDirection: "row", gap: spacing.sm, marginBottom: spacing.lg }}>
        <Button label="갤러리에서 선택" onPress={() => void selectVideo(false)} kind="secondary" style={{ flex: 1 }} />
        <Button label="카메라로 촬영" onPress={() => void selectVideo(true)} kind="secondary" style={{ flex: 1 }} />
      </View>

      <Panel style={{ alignItems: "center", borderColor: video?.validation === "valid" ? colors.lime : colors.border, borderStyle: "dashed", gap: spacing.sm, marginBottom: spacing.lg, paddingVertical: spacing.xxl }}>
        <Text style={{ color: video ? colors.lime : colors.secondary, fontFamily: styles.mono.fontFamily, fontSize: 28 }}>{video ? "✓" : "+"}</Text>
        <Text style={{ color: colors.primary, fontSize: 16, fontWeight: "700" }}>{video ? video.name : "분석할 MP4 영상을 선택하세요"}</Text>
        <Text style={styles.caption}>{video ? `${video.duration ? `${Math.round(video.duration / 100) / 10}초` : "길이 확인 중"}${video.size ? ` · ${(video.size / 1024 / 1024).toFixed(1)}MiB` : ""}` : "최대 250MiB · 3–10초"}</Text>
      </Panel>

      <Panel style={{ gap: spacing.md }}>
        <TextField keyboardType="decimal-pad" label="분석 대상 키 (cm)" onChangeText={setHeight} placeholder="예: 175" value={height} />
        <Text style={styles.caption}>프로필 키와 다르면 이번 분석에만 적용됩니다. 프로필 값을 변경하지 않습니다.</Text>
        <Text style={styles.caption}>원본 영상은 분석 목적으로만 사용되며 구체적인 보관·삭제 정책은 서비스 정책을 따릅니다.</Text>
        <Button label={video && video.validation === "valid" ? "확인하고 분석 시작" : "먼저 영상을 선택하세요"} onPress={() => void start()} disabled={!video || video.validation !== "valid"} loading={busy} />
        {busy ? <View style={{ backgroundColor: colors.surfaceRaised, height: 6, overflow: "hidden" }}><View style={{ backgroundColor: colors.lime, height: "100%", width: `${Math.max(2, progress * 100)}%` }} /></View> : null}
      </Panel>
      {video && video.validation !== "valid" ? <Text style={{ color: colors.red, fontSize: 12, marginTop: spacing.md }}>{validationMessage(video.validation)}</Text> : null}
      {error ? <View style={{ marginTop: spacing.lg }}><ErrorState message={error} /></View> : null}
    </Screen>
  );
}
