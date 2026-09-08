import React, { useEffect, useState } from "react";
import { ImagePickerAsset, launchCameraAsync, launchImageLibraryAsync, requestCameraPermissionsAsync, requestMediaLibraryPermissionsAsync } from "expo-image-picker";
import { Pressable, Text, TextInput, View } from "react-native";
import { useRouter } from "expo-router";

import { uploadVideo } from "../src/api";
import { useAuth } from "../src/auth";
import { AppHeader, Button, Screen } from "../src/components";
import { ProfileChip } from "../src/coach-ui";
import { colors, fonts, spacing, styles } from "../src/theme";

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
      <AppHeader title="분석할 영상을 선택하세요" right={<ProfileChip height={height} onPress={() => undefined} />} />
      <Pressable onPress={() => undefined} style={{ alignItems: "center", alignSelf: "flex-end", borderColor: colors.border, borderWidth: 1, flexDirection: "row", gap: 7, marginBottom: 10, minHeight: 44, paddingHorizontal: 10 }}><Text style={styles.caption}>분석 대상</Text><Text style={{ color: colors.lime, fontFamily: fonts.mono, fontSize: 12, fontWeight: "900" }}>{height || "—"}cm</Text><Text style={styles.caption}>수정 ↓</Text></Pressable>
      <Text style={[styles.body, { marginBottom: 12 }]}>측면에서 머리부터 발끝까지 보이는 3–10초 영상을 사용하세요.</Text>

      <Pressable accessibilityLabel="촬영 가이드" accessibilityRole="button" style={{ backgroundColor: colors.surface, borderColor: colors.border, borderWidth: 1, flexDirection: "row", gap: 12, minHeight: 116, padding: 10 }}>
        <View style={{ alignItems: "center", backgroundColor: colors.background, borderColor: colors.border, borderWidth: 1, flex: 1.2, justifyContent: "center" }}><Text style={styles.eyebrow}>GUIDE VIDEO</Text><View style={{ borderColor: colors.lime, borderRadius: 22, borderWidth: 3, height: 66, marginTop: 7, opacity: 0.65, width: 31 }} /></View>
        <View style={{ flex: 1, justifyContent: "center" }}><Text style={styles.eyebrow}>촬영 가이드</Text><Text style={{ color: colors.primary, fontSize: 13, fontWeight: "800", lineHeight: 19, marginTop: 8 }}>측면 · 전신{`\n`}3–10초</Text><Text style={[styles.caption, { marginTop: 8 }]}>샘플 영상 재생 →</Text></View>
      </Pressable>

      <Pressable onPress={() => void selectVideo(false)} style={{ alignItems: "center", backgroundColor: colors.surfaceSecondary, borderColor: video?.validation === "valid" ? colors.lime : "#596158", borderStyle: video ? "solid" : "dashed", borderWidth: 1, flexDirection: "row", gap: 10, marginTop: 10, minHeight: 78, paddingHorizontal: 12 }}>
        <Text style={{ color: colors.lime, fontFamily: fonts.mono, fontSize: 27 }}>{video ? "✓" : "+"}</Text>
        <View style={{ flex: 1 }}><Text numberOfLines={1} style={{ color: colors.primary, fontSize: 12, fontWeight: "800" }}>{video ? video.name : "영상 선택 또는 촬영"}</Text><Text style={[styles.caption, { fontFamily: fonts.mono, fontSize: 9, marginTop: 5 }]}>{video ? `${video.duration ? `${Math.round(video.duration / 100) / 10}초` : "길이 확인 중"}${video.size ? ` · ${(video.size / 1024 / 1024).toFixed(1)}MiB` : ""}` : "MP4 · 최대 250MiB"}</Text></View>
        <Text style={{ borderColor: colors.border, borderWidth: 1, color: colors.primary, fontSize: 9, fontWeight: "800", padding: 8 }}>찾아보기</Text>
      </Pressable>
      <View style={{ flexDirection: "row", gap: 6, marginTop: 6 }}><Button label="갤러리" onPress={() => void selectVideo(false)} kind="secondary" style={{ flex: 1, minHeight: 44 }} /><Button label="카메라 촬영" onPress={() => void selectVideo(true)} kind="secondary" style={{ flex: 1, minHeight: 44 }} /></View>

      <View style={{ alignItems: "center", backgroundColor: colors.surface, borderColor: colors.border, borderWidth: 1, flexDirection: "row", justifyContent: "space-between", marginTop: 9, minHeight: 66, padding: 10 }}><View><Text style={{ color: colors.primary, fontSize: 11, fontWeight: "800" }}>이번 분석 대상 키</Text><Text style={[styles.caption, { fontSize: 9, marginTop: 5 }]}>프로필 기본값 · 이번 분석에만 변경</Text></View><View style={{ alignItems: "center", flexDirection: "row", gap: 4 }}><TextInput keyboardType="decimal-pad" onChangeText={setHeight} placeholder="175" placeholderTextColor={colors.muted} value={height} style={{ backgroundColor: colors.background, borderColor: colors.border, borderWidth: 1, color: colors.lime, fontFamily: fonts.mono, fontSize: 16, fontWeight: "900", height: 44, paddingHorizontal: 9, textAlign: "right", width: 66 }} /><Text style={styles.caption}>cm</Text></View></View>
      <View style={{ borderColor: colors.border, borderWidth: 1, marginTop: 8, minHeight: 44, padding: 10 }}><Text style={styles.caption}>영상 보관 및 삭제 안내</Text><Text style={[styles.caption, { fontSize: 9, lineHeight: 14, marginTop: 5 }]}>원본·렌더링 영상·상세 추론 데이터는 약 24시간 후 삭제됩니다. 리포트와 스켈레톤은 기록에 남습니다.</Text></View>
      <Button label={video && video.validation === "valid" ? "확인하고 분석 시작  →" : "먼저 영상을 선택하세요"} onPress={() => void start()} disabled={!video || video.validation !== "valid"} loading={busy} style={{ marginTop: 10 }} />
      {busy ? <View style={{ backgroundColor: colors.surfaceRaised, height: 6, overflow: "hidden", marginTop: 6 }}><View style={{ backgroundColor: colors.lime, height: "100%", width: `${Math.max(2, progress * 100)}%` }} /></View> : null}
      {video && video.validation !== "valid" ? <Text style={{ color: colors.red, fontSize: 12, marginTop: spacing.md }}>{validationMessage(video.validation)}</Text> : null}
      {error ? <Text style={{ color: colors.red, fontSize: 11, marginTop: spacing.md }}>{error}</Text> : null}
    </Screen>
  );
}
