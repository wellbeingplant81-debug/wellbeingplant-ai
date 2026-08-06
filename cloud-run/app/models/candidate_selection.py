"""Sprint74 - Best-of-N 후보 선택의 구조화된 응답."""

from typing import List, Optional

from pydantic import BaseModel


class CandidateScore(BaseModel):
    """후보 한 장에 대한 평가.

    unrequested_person이 따로 있는 이유는 그것이 점수가 아니라 실격
    사유이기 때문이다. Sprint73 실측에서 Imagen은 "top-down view of a
    ceramic bowl"이라는 프롬프트에 젊은 여성의 얼굴을 그려 넣었다.
    그 그림은 선명하고 구도도 좋았다 - 사람이 잘못 들어갔을 뿐이고,
    그 하나로 영상 전체의 character_consistency가 95에서 20으로
    무너졌다. 다른 항목이 높다고 상쇄될 성질이 아니라서 숫자로 섞지
    않는다.
    """

    candidate: int
    prompt_fidelity: int
    character_match: int
    composition: int
    unrequested_person: bool
    note: Optional[str] = None


class CandidateSelection(BaseModel):
    best_candidate: int
    candidates: List[CandidateScore]
    reason: str
