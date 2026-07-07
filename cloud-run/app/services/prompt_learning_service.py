"""
Sprint49 - Self-Learning Prompt Engine.

Sprint47 prompt_metrics(품질 판정)과 Sprint44 scene_plan(camera/
visual_type/purpose/keywords 메타데이터)을 읽어, PASS한 scene에서만
패턴 통계를 누적합니다. DB/파일/외부 서비스/LLM 호출이 전혀 없는
순수 인메모리 규칙 기반 카운터입니다 - 실패한 scene은 통계에
아예 반영하지 않습니다("배우지 않는다").

이 모듈은 절대 scene/프롬프트를 반환하거나 변경하지 않습니다 -
learn_from_scenes()는 내부 카운터만 갱신하고 아무것도 반환하지
않습니다(파이프라인 출력에 영향 없음).
"""

from collections import Counter

from app.services.asset_priority_classifier import classify_scene_importance

AI_PRIORITY_CATEGORY = "ai_priority"
PEXELS_PRIORITY_CATEGORY = "pexels_priority"

TOP_KEYWORD_LIMIT = 5


def _scene_category(scene: dict) -> str:
    return (
        AI_PRIORITY_CATEGORY
        if classify_scene_importance(scene)["prefers_ai"]
        else PEXELS_PRIORITY_CATEGORY
    )


def _most_common_key(counter: Counter):
    if not counter:
        return None
    return counter.most_common(1)[0][0]


class PromptLearningEngine:
    """
    학습 통계를 담는 인메모리 저장소. 파이프라인 실행 사이에도 상태를
    유지할 수 있도록 클래스로 분리했습니다 - 모듈 레벨 기본 인스턴스는
    이 파일 하단의 flat 함수들이 사용합니다.
    """

    def __init__(self):
        self.reset()

    def reset(self):
        self._camera_counts = Counter()
        self._visual_type_counts = Counter()
        self._purpose_counts = Counter()
        self._keyword_counts = Counter()
        self._scene_category_counts = Counter()
        self._score_sum = 0
        self._success_count = 0

    def learn_from_scenes(
        self,
        scenes: list,
        scene_plan: list,
        prompt_metrics: list,
    ) -> None:
        """
        scene 번호(scene_id)로 scenes/scene_plan/prompt_metrics를
        매칭해, prompt_metrics의 passed=True인 scene에서만 통계를
        누적합니다. passed가 아니거나 매칭되는 항목이 없는 scene은
        전부 건너뜁니다 - "실패한 프롬프트는 배우지 않는다" 원칙.
        """

        plan_by_scene = {
            item["scene_id"]: item for item in (scene_plan or [])
        }
        metrics_by_scene = {
            entry["scene_id"]: entry for entry in (prompt_metrics or [])
        }

        for scene in (scenes or []):

            scene_number = scene.get("scene")
            evaluation = metrics_by_scene.get(scene_number)

            if not evaluation or not evaluation.get("passed"):
                continue

            plan_item = plan_by_scene.get(scene_number) or {}

            camera = plan_item.get("camera")
            if camera:
                self._camera_counts[camera] += 1

            visual_type = plan_item.get("visual_type")
            if visual_type:
                self._visual_type_counts[visual_type] += 1

            purpose = plan_item.get("purpose")
            if purpose:
                self._purpose_counts[purpose] += 1

            for keyword in plan_item.get("keywords") or []:
                self._keyword_counts[keyword] += 1

            self._scene_category_counts[_scene_category(scene)] += 1

            self._score_sum += evaluation.get("score", 0)
            self._success_count += 1

    def get_best_pattern(self) -> dict:
        """
        지금까지 학습한(PASS한) scene들 중 각 항목에서 가장 자주 나온
        값을 반환합니다. 아직 학습 데이터가 없으면 해당 필드는
        None(keywords는 빈 리스트)입니다.
        """

        return {
            "camera": _most_common_key(self._camera_counts),
            "visual_type": _most_common_key(self._visual_type_counts),
            "purpose": _most_common_key(self._purpose_counts),
            "keywords": [
                keyword
                for keyword, _ in self._keyword_counts.most_common(TOP_KEYWORD_LIMIT)
            ],
            "scene_category": _most_common_key(self._scene_category_counts),
        }

    def get_learning_summary(self) -> dict:
        """전체 학습 통계 스냅샷을 반환합니다."""

        average_score = (
            self._score_sum / self._success_count
            if self._success_count else 0.0
        )

        return {
            "success_count": self._success_count,
            "average_score": average_score,
            "camera_frequency": dict(self._camera_counts),
            "visual_type_frequency": dict(self._visual_type_counts),
            "purpose_frequency": dict(self._purpose_counts),
            "keyword_frequency": dict(self._keyword_counts),
            "scene_category_frequency": dict(self._scene_category_counts),
        }


_default_engine = PromptLearningEngine()


def learn_from_scenes(scenes: list, scene_plan: list, prompt_metrics: list) -> None:
    _default_engine.learn_from_scenes(scenes, scene_plan, prompt_metrics)


def get_best_pattern() -> dict:
    return _default_engine.get_best_pattern()


def get_learning_summary() -> dict:
    return _default_engine.get_learning_summary()


def reset_learning() -> None:
    """기본 인스턴스를 초기화합니다 - 주로 테스트에서 사용합니다."""
    _default_engine.reset()
