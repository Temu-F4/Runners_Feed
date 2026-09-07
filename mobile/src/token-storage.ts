import { Platform } from "react-native";
import * as SecureStore from "expo-secure-store";

function webStorage() {
  return typeof globalThis.localStorage === "undefined" ? null : globalThis.localStorage;
}

export async function getStoredToken(key: string) {
  if (Platform.OS === "web") return webStorage()?.getItem(key) ?? null;
  return SecureStore.getItemAsync(key);
}

export async function setStoredToken(key: string, value: string) {
  if (Platform.OS === "web") {
    webStorage()?.setItem(key, value);
    return;
  }
  await SecureStore.setItemAsync(key, value);
}

export async function deleteStoredToken(key: string) {
  if (Platform.OS === "web") {
    webStorage()?.removeItem(key);
    return;
  }
  await SecureStore.deleteItemAsync(key);
}
