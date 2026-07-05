import argparse
import os
import sys

import requests

API_URL = "https://api.elevenlabs.io/v1/voices"


def build_parser():

    return argparse.ArgumentParser(
        description="ElevenLabs Voice 목록을 조회하여 표로 출력합니다.",
    )


def fetch_voices(api_key: str):

    response = requests.get(
        API_URL,
        headers={"xi-api-key": api_key},
    )

    response.raise_for_status()

    return response.json()["voices"]


def format_labels(labels: dict) -> str:

    if not labels:
        return "-"

    return ", ".join(f"{key}={value}" for key, value in labels.items())


def print_table(headers, rows):

    widths = [
        max(len(str(row[i])) for row in ([headers] + rows))
        for i in range(len(headers))
    ]

    def format_row(row):
        return " | ".join(
            str(cell).ljust(widths[i])
            for i, cell in enumerate(row)
        )

    print(format_row(headers))
    print("-+-".join("-" * width for width in widths))

    for row in rows:
        print(format_row(row))


def main():

    sys.stdout.reconfigure(encoding="utf-8")

    build_parser().parse_args()

    api_key = os.getenv("ELEVENLABS_API_KEY")

    if not api_key:
        print("ELEVENLABS_API_KEY 환경변수가 설정되어 있지 않습니다.")
        sys.exit(1)

    try:
        voices = fetch_voices(api_key)
    except requests.exceptions.RequestException as exc:
        print(f"Voice 목록 조회 실패: {exc}")
        sys.exit(1)

    headers = ["Name", "Voice ID", "Labels", "Preview URL"]

    rows = [
        [
            voice.get("name", "-"),
            voice.get("voice_id", "-"),
            format_labels(voice.get("labels", {})),
            voice.get("preview_url", "-"),
        ]
        for voice in voices
    ]

    print_table(headers, rows)

    sys.exit(0)


if __name__ == "__main__":
    main()
