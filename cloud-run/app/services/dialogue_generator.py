"""
Sprint85 - Dialogue Generator v1 (Mock).

DialogueContext(dialogue_context_builder.py)를 받아 DialogueScript를
반환하는 최소 인터페이스만 정의한다. LLM 호출 없음, ElevenLabs 호출
없음, Planner와 연결하지 않음 - 항상 고정된 Mock 대사 2턴을 반환한다.
"""

from dataclasses import dataclass

from app.services.dialogue_context_builder import DialogueContext


@dataclass
class DialogueTurn:
    speaker: str
    purpose: str
    text: str


@dataclass
class DialogueScript:
    topic: str
    turns: list


class DialogueGenerator:

    @staticmethod
    def generate_dialogue(context: DialogueContext) -> DialogueScript:

        turns = [
            DialogueTurn(
                speaker="middle_aged_male",
                purpose="question",
                text="질문",
            ),
            DialogueTurn(
                speaker="professor",
                purpose="answer",
                text="답변",
            ),
        ]

        return DialogueScript(
            topic=context.topic,
            turns=turns,
        )
