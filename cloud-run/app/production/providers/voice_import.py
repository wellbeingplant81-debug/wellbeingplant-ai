"""
Sprint112 - 사용자가 만든 음성을 쓴다 (Epic 54, Phase 11).

TTS를 부르지 않는다. 사용자가 준 파일을 엔진이 쓰는 자리에 놓는다.

받는 모양은 넷이다 - 폴더, 파일 여러 개, ZIP, 그리고 그것들이 섞인
목록. 펴는 일은 incoming_files가 한다(이미지와 같은 코드다).

엔진이 쓰는 자리
----------------
audio_policy가 정한다. tts.mp3가 아니다.

    scene별   {project}/audio/scenes/scene{N}.wav
    전체      {project}/audio/voice.wav

scene별 파일이 있어야 하는 이유가 있다. subtitle_service는 scene
오디오 개수와 scene 개수가 다르면 예외를 던지고(실측: subtitle_service
:521), scene_timeline과 technical_validation도 같은 파일을 센다.
자막 시각이 그 길이들에서 나오기 때문이다.

포맷도 정책을 따른다 - 24kHz mono PCM. audio_policy가 있는 이유가
"혹시 다른 소스가 섞여 들어와도 파이프라인 전체가 한 포맷으로
수렴한다"이고, 밖에서 온 mp3야말로 그 다른 소스다. 확장자만 .wav로
바꿔 놓으면 이름이 거짓말을 한다. 그래서 정책 포맷으로 맞춰 넣되,
길이는 건드리지 않는다.

한 파일만 준 경우
-----------------
scene이 여럿이면 그것은 나레이션 전체다. 잘라서 scene에 나눠 담지
않는다 - 어디가 경계인지 우리가 알 수 없고, 자르는 것은 자동 수정이다.
전체 나레이션 자리(voice.wav)에 놓고, scene별 파일이 없다는 것을
경고한다.

길이
----
재기만 한다. 고치지 않는다. 늘리지 않는다. 이어붙이지 않는다.

예상 길이는 Duration Gate가 쓰는 그 estimator를 그대로 부른다. 두
곳이 다른 값을 내면 화면이 통과라고 한 것이 게이트에서 걸린다.

키 이름
-------
asset_path / asset_type은 이미지 단계가 이미 쓰고 있다(Sprint110).
같은 키에 음성을 쓰면 이미지 경로가 사라진다 - 이 저장소에서 한
슬롯을 두 곳에서 쓰는 구조는 이미 여러 번 사고를 냈다. 그래서 음성은
voice_path라는 제 칸을 쓰고, scene dict에 섞지 않고 따로 돌려준다.
"""

import os
import shutil
import subprocess

from app.production import source_modes, stages
from app.production.providers import incoming_files
from app.production.stage_provider import (
    STANDARD,
    ProviderCapabilities,
    StageProvider,
)
from app.services import audio_policy, duration_estimator, duration_optimizer

VOICE_IMPORT = "voice_import"

# 받아 주는 확장자. ffmpeg가 디코딩할 수 있는 것들이다.
SUPPORTED_SUFFIXES = (".wav", ".mp3", ".m4a", ".aac", ".flac", ".ogg")

AUDIO_DIRNAME = "audio"
SCENES_DIRNAME = "scenes"

# 사용자가 직접 녹음하거나 고른 음성이다. step02가 AI Image에 주는
# 값과 같은 자리이므로 같은 1.0으로 둔다.
CONFIDENCE = 1.0

# 예상 길이와 얼마나 벌어지면 말할 것인가. Duration Optimizer가 쓰는
# 허용 오차를 그대로 쓴다 - 새 숫자를 만들지 않는다.
TOLERANCE_SECONDS = duration_optimizer.TOLERANCE_SECONDS

# Sprint169 - 이름 대신 실제 자리를 쓴다. 묶인 프로그램을 받은
# 사람의 PC에는 PATH에 ffmpeg가 없다 - 그때 나는 오류는
# FileNotFoundError뿐이고, 무엇을 깔아야 하는지 알 수 없다.
#
# 부르는 명령도 인자도 그대로다. 어디에 있는 것을 부르는가만
# 바뀐다.
from app.services import media_tools

FFMPEG = media_tools.resolve(media_tools.FFMPEG)


class VoiceImportError(ValueError):
    """준 음성을 쓸 수 없다.

    무엇이 왜 안 되는지 적는다 - 사람이 고쳐서 다시 넣을 수 있어야
    한다."""


def _duration(path: str) -> float:
    """실측 길이. Duration Optimizer가 쓰는 그 ffprobe 호출이다."""

    return duration_optimizer.get_audio_duration(path)


def _normalize(source: str, target: str) -> None:
    """
    정책 포맷(24kHz mono PCM)으로 맞춰 넣는다.

    길이는 손대지 않는다 - 샘플레이트와 채널, 코덱만 맞춘다. 입력이
    이미 정책과 같으면 ffmpeg는 리샘플러를 태우지 않으므로 추가 손실이
    없다(audio_policy 참고).
    """

    command = [FFMPEG, "-y", "-i", source] + audio_policy.pcm_output_args()
    command.append(target)

    result = subprocess.run(command, capture_output=True, text=True,
                            encoding="utf-8", errors="replace")

    if result.returncode != 0 or not os.path.exists(target):
        raise VoiceImportError(
            f"음성을 읽을 수 없습니다: {os.path.basename(source)}. "
            "다른 형식으로 저장한 뒤 다시 넣어 주십시오."
        )


def _count_warnings(scene_count: int, voice_count: int) -> list:
    if scene_count == voice_count:
        return []

    if voice_count < scene_count:
        missing = list(range(voice_count + 1, scene_count + 1))
        return [
            f"Scene {scene_count}개, 음성 {voice_count}개 - "
            f"Scene {', '.join(str(n) for n in missing)}의 음성이 없습니다."
        ]

    return [
        f"Scene {scene_count}개, 음성 {voice_count}개 - "
        f"뒤쪽 {voice_count - scene_count}개는 쓰이지 않습니다."
    ]


def _duration_warnings(measured: float, expected: float) -> list:
    if measured < expected - TOLERANCE_SECONDS:
        return [
            f"음성이 영상보다 짧습니다 - 예상 {expected:.1f}초, "
            f"실제 {measured:.1f}초."
        ]

    if measured > expected + TOLERANCE_SECONDS:
        return [
            f"음성이 영상보다 깁니다 - 예상 {expected:.1f}초, "
            f"실제 {measured:.1f}초."
        ]

    return []


class VoiceImportProvider(StageProvider):
    """사용자가 준 음성을 받는다. 만들지 않는다."""

    def __init__(self):
        self.capabilities = ProviderCapabilities(
            name=VOICE_IMPORT,
            stage=stages.VOICE,
            quality_tier=STANDARD,
            # GENERATE가 없다. TTS를 부르지 않는다.
            supported_source_modes=(source_modes.IMPORT, source_modes.MANUAL),
            description=(
                "직접 만든 음성을 씁니다. 폴더·여러 파일·ZIP을 받고 "
                "API를 호출하지 않습니다."
            ),
        )

    def import_content(self, raw, request=None):
        self._require(source_modes.IMPORT)

        return self._place(raw, request)

    def accept_manual(self, payload, request=None):
        self._require(source_modes.MANUAL)

        return self._place(payload, request)

    def _place(self, payload, request) -> dict:
        """
        준 음성을 엔진이 쓰는 자리에 놓는다.

        원본은 손대지 않는다 - 정책 포맷으로 맞춘 사본만 놓는다.
        """

        if request is None:
            raise ValueError("이 단계에 필요한 값이 없습니다: ['project_path', 'scenes']")

        request.require("project_path", "scenes")

        project_path = request.project_path
        scenes = request.scenes

        audio_dir = os.path.join(project_path, AUDIO_DIRNAME)
        scenes_dir = os.path.join(audio_dir, SCENES_DIRNAME)

        # 압축을 푸는 자리. 실패하면 아무것도 남기지 않으려고 먼저
        # 전부 모은 뒤에 옮긴다.
        workspace = os.path.join(audio_dir, "_import")
        os.makedirs(workspace, exist_ok=True)

        try:
            collected = incoming_files.collect(
                payload, workspace, SUPPORTED_SUFFIXES, VoiceImportError,
                "음성",
            )

            single_whole_narration = (
                len(collected) == 1 and len(scenes) > 1
            )

            if single_whole_narration:
                placed, voice_path = [], self._place_whole(
                    collected[0], audio_dir,
                )
            else:
                placed, voice_path = self._place_scenes(
                    collected, scenes, scenes_dir,
                ), None
        finally:
            shutil.rmtree(workspace, ignore_errors=True)

        measured = (
            _duration(voice_path) if voice_path
            else sum(voice["seconds"] for voice in placed)
        )
        expected = duration_estimator.estimate_script_duration(
            [{"narration": scene.get("narration") or ""} for scene in scenes],
        )

        warnings = []

        if voice_path:
            warnings.append(
                f"음성 1개를 나레이션 전체로 놓았습니다 - Scene "
                f"{len(scenes)}개의 자막 시각을 내려면 Scene마다 하나씩 "
                "있어야 합니다."
            )
        else:
            warnings.extend(_count_warnings(len(scenes), len(collected)))

        warnings.extend(_duration_warnings(measured, expected))

        return {
            "voices": placed,
            "voice_path": voice_path,
            "scene_count": len(scenes),
            "voice_count": len(collected),
            "measured_seconds": round(measured, 2),
            "expected_seconds": round(expected, 2),
            "warnings": warnings,
        }

    def _place_whole(self, source: str, audio_dir: str) -> str:
        """나레이션 전체 자리. 자르지 않는다."""

        os.makedirs(audio_dir, exist_ok=True)
        target = os.path.join(audio_dir, audio_policy.VOICE_FILENAME)

        _normalize(source, target)
        self._require_playable(source, target)

        return target

    def _place_scenes(self, collected, scenes, scenes_dir) -> list:
        os.makedirs(scenes_dir, exist_ok=True)
        placed = []

        for index, scene in enumerate(scenes):
            if index >= len(collected):
                break

            number = scene.get("scene", index + 1)
            source = collected[index]
            target = os.path.join(
                scenes_dir, audio_policy.scene_audio_filename(number),
            )

            _normalize(source, target)
            seconds = self._require_playable(source, target)

            placed.append({
                "scene": number,
                "name": os.path.basename(source),
                "source": source,
                "voice_path": target,
                "asset_type": "voice",
                "provider": VOICE_IMPORT,
                "confidence": CONFIDENCE,
                "seconds": round(seconds, 2),
            })

        return placed

    def _require_playable(self, source: str, target: str) -> float:
        """
        재생할 수 있는지 본다. 길이가 0이면 놓아 봐야 렌더에서 죽는다.

        여기서 거절하면 사용자는 파일을 고쳐서 다시 넣으면 된다.
        """

        seconds = _duration(target)

        if seconds <= 0:
            os.remove(target)
            raise VoiceImportError(
                f"재생할 수 없는 음성입니다: {os.path.basename(source)}. "
                "길이를 읽지 못했습니다."
            )

        return seconds
