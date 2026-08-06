"""
Sprint93 - Metadata Intelligence 이식 (Epic 47).

OneDrive 저장소의 app/services/description_generator.py(Epic 17)를
가져왔다. Gemini를 호출하지 않는다 - Script의 script 텍스트와
config.DESCRIPTION_TEMPLATE(의료 안내 문구/CTA)를 조합할 뿐이다.
창의적 문구가 필요한 제목과 달리 설명은 정확성/일관성이 더 중요해
고정 템플릿으로 조립한다.

원본과 다른 곳이 하나다. longform 가지를 가져오지 않았다.

원본은 render_profile=="longform"일 때만 타임스탬프/실천 방법/주의사항
섹션을 만들고, 그러려면 duration_estimator가 필요하다. 이 저장소의
엔진은 longform을 만들지 않는다(Sprint91에서 render_profile을 가져오지
않기로 한 것과 같은 사실이다). 없는 산출물을 위해 추정기를 끌고 오면
쓰이지 않는 코드가 남고, 나중에 누군가 그것을 실제 경로로 오해한다.

shorts 경로는 원본과 완전히 같다 - render_profile이 None이거나
"shorts"일 때 원본이 타는 길이 정확히 이 길이다.
"""

from typing import Optional

from app import config


def build_summary(script_data: dict) -> str:
    return script_data.get("script") or ""


def _build_cta_text(cta_link: Optional[str] = None) -> str:
    if not cta_link:
        return config.DEFAULT_CTA_TEXT
    return f"{config.DEFAULT_CTA_TEXT}\n{cta_link}"


def generate_description(
    script_data: dict,
    hashtags: list,
    cta_link: Optional[str] = None,
) -> str:
    summary = build_summary(script_data)
    hashtag_line = " ".join(hashtags)
    cta_text = _build_cta_text(cta_link)

    return config.DESCRIPTION_TEMPLATE.format(
        summary=summary,
        medical_notice=config.MEDICAL_DISCLAIMER_TEXT,
        cta=cta_text,
        hashtags=hashtag_line,
    )
