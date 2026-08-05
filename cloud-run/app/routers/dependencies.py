"""
Sprint65 - 라우터 공용 의존성.

project_id를 실제 경로로 바꾸는 일은 여러 라우터가 똑같이 필요로
하는데, 잘못 다루면 요청 하나로 output 밖을 건드릴 수 있는 부분이라
한 곳에만 둔다. project_service가 던지는 예외를 HTTP 상태코드로
옮기는 것이 이 모듈의 전부다.
"""

from fastapi import HTTPException

from app.services import project_service


def project_path_or_404(project_id: str) -> str:
    """
    project_id를 검증된 프로젝트 경로로 바꾼다.

    형식이 잘못됐으면 400, 그런 프로젝트가 없으면 404를 낸다. 어느
    쪽이든 서비스 함수는 호출되지 않는다.
    """

    try:
        return project_service.resolve_project_path(project_id)

    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
