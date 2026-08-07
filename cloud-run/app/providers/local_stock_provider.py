"""
Sprint150 - 내 PC의 자료로 scene을 채운다 (Epic 57, Phase 1).

돈이 들지 않는 제작의 그림 쪽이다. 모델을 부르지 않고, 이미 가지고
있는 파일 중에서 고른다.

어떻게 고르는가
---------------
    scene의 image_prompt
      -> extract_search_query   (Pexels 검색이 쓰던 그 추출기)
      -> local_library.search   (파일 이름에서 끊어 낸 낱말과 겹치는 것)
      -> 가장 많이 겹치는 것

없으면 실패한다
---------------
안 맞는 그림을 억지로 넣지 않고, AI로 넘어가지도 않는다. 무료로
만들겠다고 해 놓고 조용히 Imagen을 부르면 그때부터 돈이 든다 -
Sprint130이 정한 규칙(고른 Provider가 실패하면 스톡으로 대체하지
않는다) 덕분에 여기서 던지면 그대로 멈춘다.

무엇이 없어서 멈췄는지 말한다. 사람이 파일 이름을 고치거나 자료를
더 넣으면 되는 일이다.

영상도 쓴다
-----------
videos 폴더의 파일이 걸리면 첫 프레임을 뽑아 쓴다 - 스톡 영상을
받았을 때 엔진이 하던 것과 같다. 새 방식을 만들지 않는다.
"""

import os
import shutil
import subprocess

from app.services import local_library
from app.services.search_query_extractor import extract_search_query


class LocalStockUnavailable(RuntimeError):
    """내 PC 자료로는 이 scene을 채울 수 없다.

    무엇이 없어서인지 적는다 - 사람이 고쳐서 다시 할 수 있어야 한다."""


def _keywords(image_prompt: str) -> list:
    """
    프롬프트에서 찾을 낱말을 뽑는다.

    스톡 검색이 쓰던 추출기를 그대로 쓴다 - 여기서 새 규칙을 만들면
    같은 프롬프트가 자리마다 다르게 읽힌다.
    """

    query = extract_search_query(image_prompt or "")

    words = [w.strip().lower() for w in query.split() if w.strip()]

    # 한국어 프롬프트는 추출기가 영어 낱말을 못 찾을 수 있다. 그때는
    # 원문에서 끊어 낸다 - 파일 이름도 한국어일 것이기 때문이다.
    if not words:
        words = [
            w.strip().lower()
            for w in local_library._SPLIT.split(image_prompt or "")
            if w.strip()
        ]

    return words


def _first_frame(video_path: str, output_file: str) -> None:
    """
    영상의 첫 프레임. 엔진이 스톡 영상에 하던 것과 같다.

    ffmpeg는 UTF-8로 말하는데 Windows의 기본값은 cp949다. text=True에
    맡기면 한국어 파일 이름이 섞인 순간 stderr를 읽다가 죽고, 그러면
    "무엇이 잘못됐는가" 대신 알아볼 수 없는 예외가 튄다 - 한국어
    이름을 쓰라고 권하는 기능이 정작 한국어 앞에서 무너진다.

    그래서 UTF-8로 읽되, 읽히지 않는 바이트는 버리지 않고 자리를
    남긴다. 메시지가 조금 지저분해도 사라지는 것보다 낫다.
    """

    result = subprocess.run(
        ["ffmpeg", "-y", "-i", video_path, "-frames:v", "1", "-q:v", "2",
         output_file],
        capture_output=True, encoding="utf-8", errors="replace",
    )

    if result.returncode != 0:
        raise LocalStockUnavailable(
            "영상에서 첫 프레임을 꺼내지 못했습니다: "
            f"{(result.stderr or '').strip()[-200:]}"
        )


def find(project_path: str, image_prompt: str):
    """
    이 scene에 쓸 파일을 고른다. 없으면 None.

    그림을 먼저 보고, 없으면 영상을 본다 - 영상은 프레임을 꺼내야
    하므로 손이 더 간다.
    """

    index = local_library.load(project_path)
    words = _keywords(image_prompt)

    for kind in (local_library.IMAGES, local_library.VIDEOS):
        found = local_library.search(index, words, kind=kind)

        if found:
            return found[0]

    return None


def generate_image(prompt: str, output_file: str) -> str:
    """
    고른 파일을 output_file에 놓는다. 만들지 않는다 - 고를 뿐이다.

    다리(asset_integration_service)가 부르는 이름이 generate_image라
    이름을 맞춘다. 하는 일은 "고르기"이고, 그 사실은 이 설명이 든다.
    """

    project_path = os.path.dirname(os.path.dirname(output_file))

    index = local_library.load(project_path)

    if not (index.get("items") or []):
        raise LocalStockUnavailable(
            "내 PC 자료 목록이 비어 있습니다. 폴더를 먼저 훑으십시오."
        )

    picked = find(project_path, prompt)

    if picked is None:
        raise LocalStockUnavailable(
            f"'{extract_search_query(prompt) or prompt}'에 맞는 자료를 "
            "찾지 못했습니다. 파일 이름에 그 낱말을 넣거나 자료를 "
            "더 넣으십시오."
        )

    os.makedirs(os.path.dirname(output_file), exist_ok=True)

    if picked["kind"] == local_library.VIDEOS:
        _first_frame(picked["path"], output_file)
    else:
        shutil.copyfile(picked["path"], output_file)

    print(f"STEP02 LOCAL STOCK - {picked['name']} "
          f"({picked['kind']}) · 낱말 {', '.join(picked['tags'][:4])}")

    return output_file
