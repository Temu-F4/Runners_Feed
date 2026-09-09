import argparse
import json
import os
from pathlib import Path

from scripts.Agent.report_format import render_report
from scripts.Agent.exercise_video_tool import get_exercise_video_tool
from scripts.Agent.prompts import PERSONA, INSTRUCTION, INPUT_DATA


def main(features_path, project_dir, videos_path=None):
    from dotenv import load_dotenv
    from langchain_openai import ChatOpenAI
    from langchain_core.prompts import ChatPromptTemplate
    from langchain_core.output_parsers import StrOutputParser

    features = json.loads(features_path.read_text(encoding="utf-8"))
    evidence_path = Path(__file__).parent / "evidence" / "papers.json"
    papers = json.loads(evidence_path.read_text(encoding="utf-8"))
    expected = {"paper_03", "paper_06", "paper_07", "paper_11", "paper_running_technique"}
    if {p["id"] for p in papers} != expected or len(papers) != 5:
        raise ValueError("논문 근거 5편이 모두 필요합니다.")
    if any(not p["pages"] or any(not page["text"].strip() for page in p["pages"]) for p in papers):
        raise ValueError("논문 페이지 본문이 비어 있습니다.")
    evidence = json.dumps(papers, ensure_ascii=False)
    load_dotenv(project_dir / ".env")
    load_dotenv(project_dir / "Coach" / ".env")
    api_key = os.getenv("OPENAI_API_KEY") or os.getenv("_OPENAI_API_KEY")
    if not api_key:
        raise ValueError(".env에 OPENAI_API_KEY를 설정하세요.")
    prompt = ChatPromptTemplate.from_messages([
        ("system", PERSONA + "\n" + INSTRUCTION), ("human", INPUT_DATA),
    ])
    model = ChatOpenAI(model="gpt-5-nano", api_key=api_key, timeout=180, max_retries=2)
    chain = prompt | model | StrOutputParser()
    inputs = {"features": json.dumps(features, ensure_ascii=False), "paper_evidence": evidence}
    for attempt in range(3):
        summary = chain.invoke(inputs).strip()
        if summary and len(summary) <= 250 and not any(t in summary for t in ("\n", "paper_", "PDF p.", "```")):
            break
        inputs["paper_evidence"] += "\n출력은 250자 이하, 줄바꿈/내부 인용 표기 없는 한 문장만 작성하세요."
    else:
        raise ValueError("AI 한줄평 형식을 검증하지 못했습니다.")
    videos = (json.loads(videos_path.read_text(encoding="utf-8")) if videos_path
              else get_exercise_video_tool().invoke({"features": features}))
    report = render_report(features, summary, videos)
    output = features_path.parent / "running_report.json"
    temporary = output.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    temporary.replace(output)
    print(f"보고서 저장: {output}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("project_dir", type=Path)
    parser.add_argument("run_folder")
    parser.add_argument("--videos", type=Path, help="title/url을 가진 영상 목록 JSON")
    args = parser.parse_args()
    main(args.project_dir / "Coach/run" / args.run_folder / "outputs/feature_results.json",
         args.project_dir, args.videos)
