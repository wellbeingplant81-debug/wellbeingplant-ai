import json

from google import genai

from app import config
from app.prompts.script_prompt import SCRIPT_PROMPT
from app.prompts.viral_script_prompt import VIRAL_SCRIPT_PROMPT
from app.services.duration_estimator import DEFAULT_CHARS_PER_SECOND


client = genai.Client(
    vertexai=True,
    project="wellbeingplant-ai",
    location="global",
)


def generate_script(
    topic: str,
    target_duration: int = 45,
    scene_count: int = 6,
    retry_feedback: str = "",
    chars_per_second: float = DEFAULT_CHARS_PER_SECOND,
):

    template = VIRAL_SCRIPT_PROMPT if config.ENABLE_VIRAL_WRITER else SCRIPT_PROMPT

    # Sprint69-2 - Duration Gate Adaptive Retry: duration_estimator와
    # 동일한 계수로 목표 글자 수를 역산해 Writer 프롬프트에 명시한다 -
    # 이전에는 "약 45초"라는 서술적 문구만 있어 실제 필요한 글자 수에
    # 대한 신호가 없었다.
    #
    # Sprint97 - Provider-Aware Calibration: chars_per_second를 호출부
    # (duration_gate)가 tts_provider에 맞게 override할 수 있게 한다.
    # 기본값은 기존 DEFAULT_CHARS_PER_SECOND(Chirp)와 동일해 인자를
    # 생략하면 지금까지와 완전히 동일하게 동작한다.
    target_chars = round(target_duration * chars_per_second)

    prompt = template.substitute(
        topic=topic,
        target_duration=target_duration,
        scene_count=scene_count,
        target_chars=target_chars,
        retry_feedback=retry_feedback,
    )

    print("\n" + "=" * 80)
    print("SCRIPT PROMPT")
    print("=" * 80)
    print(prompt)
    print("=" * 80)

    response = client.models.generate_content(
        model="gemini-2.5-pro",
        contents=prompt,
    )

    text = response.text.strip()

    if text.startswith("```json"):
        text = (
            text.replace("```json", "")
            .replace("```", "")
            .strip()
        )

    print("\n" + "=" * 80)
    print("RAW GEMINI RESPONSE")
    print("=" * 80)
    print(text)
    print("=" * 80)

    data = json.loads(text)

    print("\n" + "=" * 80)
    print("SCENE 1 KEYS")
    print("=" * 80)
    print(data["scenes"][0].keys())
    print("=" * 80)

    return {
        "success": True,
        "data": data,
    }