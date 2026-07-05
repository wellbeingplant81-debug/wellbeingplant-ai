from app.services.search_query_extractor import extract_search_query


def _keywords_for_scene(scene: dict) -> set:
    """
    scene의 키워드 집합을 얻습니다. step02_assets가 이미 계산해 둔
    search_query가 있으면 그대로 재사용하고(중복 계산 방지), 없으면
    image_prompt에서 추출합니다.
    """

    query = scene.get("search_query")

    if not query:
        query = extract_search_query(scene.get("image_prompt", ""))

    return set(query.split()) if query else set()


def _pair_continuity(scene_a: dict, scene_b: dict) -> float:
    """
    두 scene의 키워드 집합에 대한 Jaccard 유사도(교집합/합집합)를
    연속성 점수로 사용합니다. 순수 함수입니다.
    """

    keywords_a = _keywords_for_scene(scene_a)
    keywords_b = _keywords_for_scene(scene_b)

    if not keywords_a or not keywords_b:
        return 0.0

    union = keywords_a | keywords_b

    if not union:
        return 0.0

    return len(keywords_a & keywords_b) / len(union)


def analyze_flow(scenes: list) -> dict:
    """
    Scene 리스트를 분석해 인접 scene 간 연속성 점수와 전체 흐름
    점수를 계산합니다. Scene은 절대 재정렬하지 않습니다 - overlay
    분석 결과만 반환하는 순수 함수입니다.

    반환값: {
        "pairs": [{"from_scene": int, "to_scene": int, "continuity_score": float}, ...],
        "overall_flow_score": float,
    }
    """

    sorted_scenes = sorted(scenes, key=lambda scene: scene["scene"])

    pairs = []

    for previous, current in zip(sorted_scenes, sorted_scenes[1:]):
        pairs.append({
            "from_scene": previous["scene"],
            "to_scene": current["scene"],
            "continuity_score": _pair_continuity(previous, current),
        })

    overall_flow_score = (
        sum(pair["continuity_score"] for pair in pairs) / len(pairs)
        if pairs else 1.0
    )

    return {
        "pairs": pairs,
        "overall_flow_score": overall_flow_score,
    }


def annotate_scenes_with_flow(scenes: list) -> list:
    """
    각 scene에 flow_continuity(직전 scene과의 연속성 점수, 첫 scene은
    None)를 추가한 새 scene 리스트를 반환합니다. 입력 scene들은
    변경하지 않고, 순서도 절대 바꾸지 않습니다 (overlay 원칙).
    """

    sorted_scenes = sorted(scenes, key=lambda scene: scene["scene"])

    result = []
    previous = None

    for scene in sorted_scenes:

        enriched = dict(scene)
        enriched["flow_continuity"] = (
            _pair_continuity(previous, scene) if previous is not None else None
        )

        result.append(enriched)
        previous = scene

    return result
