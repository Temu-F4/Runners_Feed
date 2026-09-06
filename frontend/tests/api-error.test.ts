import assert from "node:assert/strict";
import test from "node:test";

import { getApiErrorMessage } from "../lib/api-error.ts";

test("FastAPI video validation errors have an actionable message", () => {
  const message = getApiErrorMessage(
    {
      detail: [
        {
          type: "literal_error",
          loc: ["body", "content_type"],
          msg: "Input should be 'video/mp4' or 'video/quicktime'",
        },
      ],
    },
    422,
  );

  assert.notEqual(message, "[object Object]");
  assert.equal(
    message,
    "영상 형식을 확인할 수 없습니다. MP4 또는 MOV 파일을 다시 선택해 주세요.",
  );
});

test("plain API details remain visible", () => {
  assert.equal(
    getApiErrorMessage({ detail: "Uploaded video is empty" }, 400),
    "Uploaded video is empty",
  );
});

test("unknown error payloads use the HTTP fallback", () => {
  assert.equal(getApiErrorMessage({}, 503), "요청에 실패했습니다. (503)");
});
