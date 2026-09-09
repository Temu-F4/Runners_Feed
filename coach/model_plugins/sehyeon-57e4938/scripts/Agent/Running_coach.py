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
parser.add_argument("project_dir", type=Path)
parser.add_argument("run_folder", type=str)
args = parser.parse_args()

PROJECT_DIR = args.project_dir
RUN_FOLDER = args.run_folder
RUN_DIR = PROJECT_DIR / "run" / RUN_FOLDER

load_dotenv(PROJECT_DIR / ".env")
api_key = os.environ.get("OPENAI_API_KEY")




def main(features_path: Path):
    # 1. feature_extract 결과
    with open(features_path, "r", encoding="utf-8") as file:
        features = json.load(file)

    # Service-normalized values include the fixed score policies used by the
    # app. Keep frame series out of the prompt to avoid unnecessary tokens.
    features = {
        feature_id: {
            key: value
            for key, value in feature.items()
            if key not in {"series", "description"}
        }
        for feature_id, feature in features.items()
        if isinstance(feature, dict)
    }


    # 2. 관련 논문에서 미리 정리한 근거
    paper_evidence = PAPERS[0]


    # 3. 프롬프트
    prompt = ChatPromptTemplate.from_messages([
        (
            "system",
            f"{PERSONA}\n{INSTRUCTION}"
        ),
        (
            "human",
            INPUT_DATA
        ),
    ])


    # 4. LLM
    model = ChatOpenAI(
        model=os.environ.get("COACH_LLM_MODEL", "gpt-5-nano"),
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
        )
    })


    # 7. 결과 저장
    with open(features_path.parent / "running_report.md", "w", encoding="utf-8") as file:
        file.write(report)

    print(report)

if __name__ == "__main__":
    features_path = RUN_DIR / "outputs" / "feature_results.service.json"
    main(features_path)
