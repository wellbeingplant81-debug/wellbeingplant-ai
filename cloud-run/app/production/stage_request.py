"""
Sprint103 - 단계 요청 (Epic 54, Phase 2).

Provider에게 "이걸 만들어 달라"고 넘기는 것이다.

단계마다 다른 클래스를 만들지 않았다. 지금 파이프라인이 각 단계에
넘기는 값이 topic/project_path/channel/scenes/data 다섯 가지로 겹치고,
다섯 개의 거의 같은 클래스를 두면 화면과 Plan이 그것들을 다시 하나로
묶는 코드를 갖게 된다.

Provider는 자기가 필요한 것만 읽는다 - 없으면 없는 대로 실패한다.
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class StageRequest:

    # 사람이 적은 주제. Script 단계가 쓴다.
    topic: str = ""
    # 산출물이 쌓이는 곳. 네 단계가 전부 쓴다.
    project_path: str = ""
    # 채널별 시각 일관성. Image 단계가 쓴다.
    channel: str = "wellbeing"
    # 앞 단계가 만든 scene 목록. Image/Voice가 쓴다.
    scenes: Optional[list] = None
    # step01이 만든 대본 전체. 뒤 단계가 참조한다.
    data: Optional[dict] = None
    extra: dict = field(default_factory=dict)

    def require(self, *names: str) -> None:
        """필요한 것이 없으면 만들기 전에 멈춘다."""

        missing = [n for n in names if not getattr(self, n, None)]

        if missing:
            raise ValueError(
                f"이 단계에 필요한 값이 없습니다: {missing}"
            )
