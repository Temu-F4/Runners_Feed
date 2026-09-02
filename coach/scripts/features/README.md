# feature를 구하는 파이프라인에 대한 설명.

## 주요 파일
1. features.sh : main.sh에 의해 실행되는 스크립트. features 파이프라인 실행 쉘이다.
2. utils.py : HPE데이터로부터 의미를 추출하기 위해 사용하는 도구 집합이다.
3. feature_extract.py : 피처 추출이 이뤄지는 파일. 각 피처를 구하는 함수가 정의되고 실행된다.
4. papers.py : 각 피처에 해당하는 논문의 요약본이 프롬프트 입력 가능한 형태로 저장된 파일.

## pipeline
features.sh을 실행하면 feature_extract.py 파일 하나만 실행된다.<br>
산출물은 feature_results.json이고 outputs에 저장된다.<br>
이후 다음 파이프라인인 Agent로 넘어간다.<br>