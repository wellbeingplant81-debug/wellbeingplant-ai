import argparse
import os
import sys

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.providers import elevenlabs_provider  # noqa: E402

DEFAULT_TEXT = (
    "밤마다 화장실 때문에 자주 깨시나요? "
    "그 원인은 단순한 노화가 아닐 수도 있습니다."
)

DEFAULT_OUTPUT = os.path.join("output", "test", "elevenlabs_test.mp3")


def build_parser():

    parser = argparse.ArgumentParser(
        description="지정한 ElevenLabs Voice ID로 테스트 음성을 생성합니다.",
    )

    parser.add_argument(
        "--voice-id",
        required=True,
        help="테스트할 ElevenLabs Voice ID",
    )

    parser.add_argument(
        "--text",
        default=DEFAULT_TEXT,
        help="생성할 테스트 문장 (기본값: 건강정보 쇼츠 예시 문장)",
    )

    parser.add_argument(
        "--output",
        default=DEFAULT_OUTPUT,
        help=f"저장할 mp3 경로 (기본값: {DEFAULT_OUTPUT})",
    )

    return parser


def main():

    sys.stdout.reconfigure(encoding="utf-8")

    args = build_parser().parse_args()

    if not os.getenv("ELEVENLABS_API_KEY"):
        print("ELEVENLABS_API_KEY 환경변수가 설정되어 있지 않습니다.")
        sys.exit(1)

    os.environ["ELEVENLABS_VOICE_ID"] = args.voice_id

    try:
        output_path = elevenlabs_provider.generate_voice(args.text, args.output)
    except Exception as exc:
        print(f"음성 생성 실패: {exc}")
        sys.exit(1)

    size_bytes = os.path.getsize(output_path)

    print("음성 생성 성공")
    print(f"  Voice ID  : {args.voice_id}")
    print(f"  문장      : {args.text}")
    print(f"  출력 파일 : {output_path}")
    print(f"  파일 크기 : {size_bytes:,} bytes")

    sys.exit(0)


if __name__ == "__main__":
    main()
