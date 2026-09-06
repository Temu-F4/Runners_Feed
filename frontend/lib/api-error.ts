interface FastApiErrorItem {
  loc?: unknown;
  msg?: unknown;
}

function isFastApiErrorItem(value: unknown): value is FastApiErrorItem {
  return typeof value === "object" && value !== null;
}

export function getApiErrorMessage(payload: unknown, status: number): string {
  if (
    typeof payload !== "object"
    || payload === null
    || !("detail" in payload)
  ) {
    return `요청에 실패했습니다. (${status})`;
  }

  const detail = (payload as { detail?: unknown }).detail;
  if (typeof detail === "string" && detail.trim()) return detail;

  if (Array.isArray(detail)) {
    const items = detail.filter(isFastApiErrorItem);
    const hasVideoFormatError = items.some((item) => {
      const location = Array.isArray(item.loc) ? item.loc : [];
      return location.includes("filename") || location.includes("content_type");
    });
    if (hasVideoFormatError) {
      return "영상 형식을 확인할 수 없습니다. MP4 또는 MOV 파일을 다시 선택해 주세요.";
    }

    const messages = items
      .map((item) => item.msg)
      .filter((message): message is string => typeof message === "string" && Boolean(message.trim()));
    if (messages.length > 0) return messages.join(" ");
  }

  return `요청에 실패했습니다. (${status})`;
}
