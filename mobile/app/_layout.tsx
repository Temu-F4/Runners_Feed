import React from "react";
import { Pressable, Text, View } from "react-native";
import { Stack } from "expo-router";
import { SafeAreaProvider, SafeAreaView } from "react-native-safe-area-context";

import { AuthProvider, useAuth } from "../src/auth";
import { BottomNavigation, LoadingState } from "../src/components";
import { colors, styles } from "../src/theme";

function ApplicationShell() {
  const { ready, error, retry } = useAuth();

  if (!ready) {
    return (
      <SafeAreaView style={styles.screen}>
        <LoadingState message="러너스 피드를 준비하고 있습니다." />
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView edges={["top", "bottom"]} style={styles.screen}>
      {error ? <Pressable accessibilityRole="button" onPress={() => void retry()} style={{ alignItems: "center", backgroundColor: colors.surface, borderBottomColor: colors.red, borderBottomWidth: 1, flexDirection: "row", justifyContent: "space-between", minHeight: 42, paddingHorizontal: 17 }}><Text numberOfLines={1} style={{ color: colors.red, flex: 1, fontSize: 10 }}>서버 연결을 확인해 주세요</Text><Text style={{ color: colors.primary, fontSize: 10, fontWeight: "800" }}>다시 시도</Text></Pressable> : null}
      <Stack screenOptions={{ animation: "fade", contentStyle: { backgroundColor: colors.background }, headerShown: false }} />
      <BottomNavigation />
    </SafeAreaView>
  );
}

export default function RootLayout() {
  return (
    <SafeAreaProvider>
      <AuthProvider>
        <View style={styles.screen}>
          <ApplicationShell />
        </View>
      </AuthProvider>
    </SafeAreaProvider>
  );
}
