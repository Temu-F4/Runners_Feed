import React from "react";
import { View } from "react-native";
import { Stack } from "expo-router";
import { SafeAreaProvider, SafeAreaView } from "react-native-safe-area-context";

import { AuthProvider, useAuth } from "../src/auth";
import { BottomNavigation, ErrorState, LoadingState } from "../src/components";
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

  if (error) {
    return (
      <SafeAreaView style={[styles.screen, { justifyContent: "center", padding: 20 }]}>
        <ErrorState message={error} onRetry={() => void retry()} />
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView edges={["top", "bottom"]} style={styles.screen}>
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
