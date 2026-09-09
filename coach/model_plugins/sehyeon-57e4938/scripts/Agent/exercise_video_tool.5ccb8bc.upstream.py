"""Curated video lookup tool. No RAG, web calls or extra LLM calls."""
import json
import math
from pathlib import Path
from urllib.parse import urlparse, parse_qs

CATALOG = Path(__file__).with_name("exercise_videos.json")


def valid_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def condition(feature, result):
    if not isinstance(result, dict) or result.get("range", {}).get("warning"):
        return None
    value = result.get("value")
    instruction = result.get("instruction", "")
    if not isinstance(instruction, str) or not instruction:
        return None
    if feature == "Elbow angle":
        if not isinstance(value, list) or not any(valid_number(v) for v in value):
            return None
        if result.get("range", {}).get("section") == "측정 불가":
            return None
        return "maintain" if "유지" in instruction or "good" in instruction else "adjust_arms"
    if not valid_number(value) or value < 0:
        return None
    if feature == "Amplitude of pelvis oscillation":
        return "reduce_bounce" if "튀는" in instruction and "줄" in instruction else "maintain"
    if feature in ("Trunk flexion angle", "Postural lean angle"):
        if "세우" in instruction:
            return "decrease_lean"
        if "기울이" in instruction:
            return "increase_lean"
        if "good" in instruction or "좋아요" in instruction or "유지" in instruction:
            return "maintain"
    return None


def recommend_exercise_videos(features: dict, max_per_feature: int = 1) -> list[dict]:
    """피처 판정에 맞는 사전 등록 유튜브 영상 반환. 피처당 1~2개, 미측정 제외."""
    if isinstance(max_per_feature, bool) or max_per_feature not in (1, 2):
        raise ValueError("max_per_feature must be 1 or 2")
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    states = {key: condition(key, value) for key, value in features.items()}
    # Mixed trunk/body advice must not result in a generic forward-lean drill.
    forward_allowed = all(states.get(key) == "increase_lean" for key in
                          ("Trunk flexion angle", "Postural lean angle"))
    selected, counts, seen = [], {}, set()
    for video in catalog:
        key = video["feature"]
        if states.get(key) not in video["conditions"]:
            continue
        if video["requires_forward_lean"] and not forward_allowed:
            continue
        if counts.get(key, 0) >= max_per_feature or video["url"] in seen:
            continue
        url = urlparse(video["url"])
        if url.scheme != "https" or url.hostname != "www.youtube.com" or url.path != "/watch" or not parse_qs(url.query).get("v"):
            raise ValueError("Invalid catalog YouTube URL")
        selected.append({"id": video["id"], "title": video["title"], "url": video["url"], "feature": key})
        counts[key] = counts.get(key, 0) + 1
        seen.add(video["url"])
    return selected


def get_exercise_video_tool():
    """Return a LangChain tool for future agent bind_tools usage."""
    from langchain_core.tools import StructuredTool
    return StructuredTool.from_function(recommend_exercise_videos)
