from dotenv import load_dotenv
import os
import argparse

import json
from pathlib import Path

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

from scripts.features.papers import PAPERS
from scripts.Agent.prompts import *


parser = argparse.ArgumentParser()
parser.add_argument("workspace_root", type=Path)
parser.add_argument("run_folder", type=str)
args = parser.parse_args()

WORKSPACE_ROOT = args.workspace_root
RUN_FOLDER = args.run_folder
RUN_DIR = WORKSPACE_ROOT / "run" / RUN_FOLDER

local_env = Path(__file__).resolve().parents[2] / ".env"
load_dotenv(local_env, override=False)
api_key = (
    os.environ.get("OPENAI_API_KEY")
    or os.environ.get("OPENAI_KEY")
    or os.environ.get("_OPENAI_API_KEY")
)




def main(features_path: Path):
    # 1. feature_extract 결과
    with open(features_path, "r", encoding="utf-8") as file:
        features = json.load(file)


    # 2. 관련 논문에서 미리 정리한 근거
    paper_evidence = PAPERS[0]


    # 3. 프롬프트
    prompt = ChatPromptTemplate.from_messages([
        (
            "system",
            (
                PERSONA,
                INSTRUCTION
            )
        ),
        (
            "human",
            INPUT_DATA
        ),
    ])


    # 4. LLM
    model = ChatOpenAI(
        model="gpt-5.6-luna",
        temperature=0,
        api_key=api_key
    )


    # 5. LangChain 구성
    chain = prompt | model | StrOutputParser()


    # 6. 실행
    report = chain.invoke({
        "features": json.dumps(
            features,
            ensure_ascii=False,
            indent=2,
        ),
        "paper_evidence": paper_evidence,
    })


    # 7. 결과 저장
    with open(features_path.parent / "running_report.md", "w", encoding="utf-8") as file:
        file.write(report)

    print(report)

if __name__ == "__main__":
    features_path = RUN_DIR / "outputs" / "feature_results.json"
    main(features_path)
