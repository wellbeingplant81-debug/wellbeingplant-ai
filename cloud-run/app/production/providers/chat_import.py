"""
Sprint104 - Chat Import Provider (Epic 54, Phase 3).

사용자가 ChatGPT / Claude / Gemini / DeepSeek에서 만든 대본을 붙여넣는
경로다. AI를 부르지 않으므로 비용이 0이다.

읽는 일은 chat_script_parser가 한다. 이 파일은 Provider 계약에 맞춰
그것을 부르고, 결과를 지금 엔진이 쓰는 자리(script.json)에 남긴다 -
step01_script.run()이 하던 마지막 동작과 같다. 그래야 뒤 단계들이
붙여넣은 대본인지 생성된 대본인지 구분하지 않아도 된다.

제목이 없는 것을 붙여넣으면 사용자가 적은 주제를 제목으로 쓴다.
지어내는 것이 아니다 - 사용자가 이미 준 값이고, 그것 말고 우리가
아는 제목은 없다. 주제도 없으면 거절한다.
"""

import json
import os

from app.production import source_modes, stages
from app.production.chat_script_parser import parse_script
from app.production.stage_provider import (
    STANDARD,
    ProviderCapabilities,
    StageProvider,
)

CHAT_IMPORT = "chat_import"

SCRIPT_FILENAME = "script.json"


class ChatImportScriptProvider(StageProvider):
    """붙여넣은 대본을 받는다. 생성은 하지 않는다."""

    def __init__(self):
        self.capabilities = ProviderCapabilities(
            name=CHAT_IMPORT,
            stage=stages.SCRIPT,
            quality_tier=STANDARD,
            # GENERATE가 없다. 이 Provider는 만들지 않고 받기만 한다.
            supported_source_modes=(source_modes.IMPORT,),
            description=(
                "ChatGPT/Claude/Gemini/DeepSeek에서 만든 대본을 붙여넣어 "
                "그대로 씁니다. API를 호출하지 않습니다."
            ),
        )

    def import_content(self, raw: str, request=None):
        """
        붙여넣은 텍스트를 대본으로 읽고 script.json에 남긴다.

        읽지 못하면 예외를 던진다 - 반쯤 읽은 결과로 영상을 만들지
        않는다.
        """

        self._require(source_modes.IMPORT)

        topic = getattr(request, "topic", "") if request else ""

        # 제목이 없으면 사용자가 적은 주제를 쓴다. 파서에 넘겨서
        # 처리한다 - 앞에 "제목:" 줄을 덧붙여 다시 읽히는 꼼수를 쓰면
        # JSON을 붙여넣은 경우가 깨진다(실측).
        script = parse_script(raw, default_title=topic)

        project_path = getattr(request, "project_path", "") if request else ""

        if project_path:
            self._save(script, project_path)

        return script

    @staticmethod
    def _parse_with_topic_as_title(raw: str, topic: str) -> dict:
        """제목이 빠진 붙여넣기를 주제로 메운다.

        주제 줄을 앞에 덧붙여 같은 파서로 다시 읽는다 - 파서에 예외
        경로를 만들지 않는다. 제목 말고 다른 이유로 실패한 것이라면
        여기서도 똑같이 실패한다."""

        return parse_script(f"제목: {topic}\n\n{raw}")

    @staticmethod
    def _save(script: dict, project_path: str) -> None:
        """step01_script.run()이 하던 그 자리에 그대로 남긴다."""

        os.makedirs(project_path, exist_ok=True)

        with open(
            os.path.join(project_path, SCRIPT_FILENAME), "w", encoding="utf-8",
        ) as f:
            json.dump(script, f, ensure_ascii=False, indent=4)
