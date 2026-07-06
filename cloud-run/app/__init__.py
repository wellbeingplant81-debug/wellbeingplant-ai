import os

from dotenv import load_dotenv

# app 패키지가 처음 import되는 시점(FastAPI 앱 구동, 파이프라인 스크립트
# 직접 실행, 테스트 등 어떤 진입점이든)에 cloud-run/.env를 한 번 로드한다.
# 호출자의 현재 작업 디렉터리와 무관하게 항상 이 파일 기준 상대 경로로
# .env를 찾는다. override=False(기본값)라서 Cloud Run 등에서 이미
# 설정된 실제 환경변수는 절대 덮어쓰지 않고, .env 파일이 없으면 조용히
# 아무 일도 하지 않는다 - 로컬(.env)과 배포 환경(Cloud Run 환경변수) 둘
# 다 그대로 지원된다.
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
