"""
Sprint100-3.1 - Stock Video Visual Relevance.

Pexels Video 후보는 검색어 텍스트로만 매칭되어, 검색어와는 관련 있어
보여도 실제 프레임 내용이 narration/image_prompt와 무관한 경우가 있다
(2026-07-13 Production QA에서 실측: "shocked korean woman" 검색어인데
실제 대표 프레임은 머리카락 클로즈업). 이 모듈은 후보 하나의 대표
프레임 이미지를 Gemini Vision에 보여주고, narration/image_prompt와
얼마나 관련 있는지 0.0~1.0 점수로 채점하는 순수 함수만 제공한다 -
후보를 여러 개 순회하며 최선을 고르는 오케스트레이션(다운로드/프레임
추출/폴백)은 asset_integration_service.py의 책임이다.
"""

from google import genai
from google.genai import types
from PIL import Image

from app.models.video_relevance import VideoRelevanceScore
from app.prompts.video_relevance_rubric import VIDEO_RELEVANCE_RUBRIC


MODEL_NAME = "gemini-2.5-flash"

client = genai.Client(
    vertexai=True,
    project="wellbeingplant-ai",
    location="global",
)


def score_relevance(
    frame_image_path: str, narration: str, image_prompt: str,
) -> VideoRelevanceScore:
    """
    frame_image_path의 이미지 하나를 narration/image_prompt와 비교해
    VideoRelevanceScore(score, reasoning)를 반환한다. Gemini가 유효한
    구조화 응답을 주지 않으면 예외를 던진다 - 호출자(asset_integration_
    service._select_relevant_video_candidate())가 이 후보를 건너뛰고
    다음 후보로 넘어갈 때 사용한다.
    """

    with Image.open(frame_image_path) as opened:
        opened.load()
        frame_image = opened.copy()

    scene_context = f"narration: {narration}\nimage_prompt: {image_prompt}"

    response = client.models.generate_content(
        model=MODEL_NAME,
        contents=[VIDEO_RELEVANCE_RUBRIC, scene_context, frame_image],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=VideoRelevanceScore,
        ),
    )

    if response.parsed is None:
        raise ValueError("Gemini did not return a valid structured response")

    return response.parsed
