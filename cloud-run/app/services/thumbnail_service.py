import os
import subprocess

from PIL import Image, ImageDraw, ImageFont

from app.services.render_profile import silent_video_filename, thumbnail_filename


FONT_PATH = "C:/Windows/Fonts/malgunbd.ttf"

MAX_FONT_SIZE_RATIO = 0.14
MIN_FONT_SIZE = 24
LINE_SPACING_RATIO = 0.25
SAFE_WIDTH_RATIO = 0.88
STROKE_WIDTH_RATIO = 0.09

TEXT_COLOR = (255, 221, 0)
KEYWORD_COLOR = (230, 30, 30)
OUTLINE_COLOR = (0, 0, 0)
BOX_COLOR = (0, 0, 0, 140)
BOX_PADDING_RATIO = 0.35
BOX_TOP_RATIO = 0.14


def _extract_first_frame(video_path: str, output_path: str) -> None:
    """
    Sprint124 - Thumbnail=First Frame Policy. 이미 렌더링된 무음
    합성본(video_builder.py 출력, 자막 mux 전)의 첫 프레임을 그대로
    추출한다. video_builder.py의 _effects_for_clip() 수정(첫 clip
    fade-in 제거)로 이 프레임은 더 이상 검은 화면이 아니다.
    """

    command = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-frames:v", "1",
        "-update", "1",
        output_path,
    ]

    result = subprocess.run(command, capture_output=True, text=True)

    if result.returncode != 0:
        raise Exception(f"썸네일 첫 프레임 추출 실패: {result.stderr}")


def _load_font(size):
    return ImageFont.truetype(FONT_PATH, size)


def _text_size(draw, text, font, stroke_width):
    bbox = draw.textbbox((0, 0), text, font=font, stroke_width=stroke_width)
    return bbox[2] - bbox[0], bbox[3] - bbox[1]


def _fit_font_size(draw, lines, canvas_width):
    """
    가장 넓은 줄이 SAFE_WIDTH_RATIO 안에 들어올 때까지 폰트 크기를
    MAX_FONT_SIZE_RATIO에서부터 줄여나간다 - "한눈에 읽히는 크기"를
    보장하면서도 화면 밖으로 넘치지 않게 한다.
    """

    size = max(MIN_FONT_SIZE, int(canvas_width * MAX_FONT_SIZE_RATIO))
    safe_width = canvas_width * SAFE_WIDTH_RATIO

    while size > MIN_FONT_SIZE:
        font = _load_font(size)
        stroke_width = max(1, int(size * STROKE_WIDTH_RATIO))
        widest = max(_text_size(draw, line, font, stroke_width)[0] for line in lines)
        if widest <= safe_width:
            break
        size -= 2

    return size


def _line_words_with_colors(line, keywords):
    return [
        (
            word,
            KEYWORD_COLOR if any(keyword in word for keyword in keywords) else TEXT_COLOR,
        )
        for word in line.split()
    ]


def _draw_centered_line(draw, y, words_with_colors, font, stroke_width, canvas_width):

    space_width, _ = _text_size(draw, " ", font, stroke_width)
    widths = [_text_size(draw, word, font, stroke_width)[0] for word, _ in words_with_colors]
    total_width = sum(widths) + space_width * max(0, len(words_with_colors) - 1)

    x = (canvas_width - total_width) / 2

    for (word, color), width in zip(words_with_colors, widths):
        draw.text(
            (x, y), word, font=font, fill=color,
            stroke_width=stroke_width, stroke_fill=OUTLINE_COLOR,
        )
        x += width + space_width


def _draw_headline(image_path: str, headline: dict) -> None:
    """
    Sprint124 - Thumbnail Headline Overlay. headline["lines"]를 화면
    상단부(BOX_TOP_RATIO)에 중앙 정렬로 그린다. headline["keywords"]에
    포함된(부분 일치) 단어는 빨간색, 나머지는 노란색 - 항상 검정
    외곽선(stroke)을 두르고, 가독성을 위해 텍스트 블록 뒤에 반투명
    검정 박스를 깐다.
    """

    lines = headline.get("lines") or []

    if not lines:
        return

    keywords = headline.get("keywords") or []

    image = Image.open(image_path).convert("RGBA")
    canvas_width, canvas_height = image.size
    draw = ImageDraw.Draw(image)

    font_size = _fit_font_size(draw, lines, canvas_width)
    font = _load_font(font_size)
    stroke_width = max(1, int(font_size * STROKE_WIDTH_RATIO))

    line_height = _text_size(draw, "가", font, stroke_width)[1]
    line_gap = int(font_size * LINE_SPACING_RATIO)
    block_height = len(lines) * line_height + (len(lines) - 1) * line_gap

    box_padding = int(font_size * BOX_PADDING_RATIO)
    top = canvas_height * BOX_TOP_RATIO
    box_top = max(0, top - box_padding)
    box_bottom = min(canvas_height, top + block_height + box_padding)

    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    ImageDraw.Draw(overlay).rectangle(
        [0, box_top, canvas_width, box_bottom], fill=BOX_COLOR,
    )
    image = Image.alpha_composite(image, overlay)
    draw = ImageDraw.Draw(image)

    y = top
    for line in lines:
        _draw_centered_line(
            draw, y, _line_words_with_colors(line, keywords),
            font, stroke_width, canvas_width,
        )
        y += line_height + line_gap

    image.convert("RGB").save(image_path)


def create_thumbnail(
    title: str,
    topic: str,
    project_path: str,
    channel: str = "wellbeing",
    scene1_narration: str = "",
    scene1_image_prompt: str = "",
    render_profile: dict = None,
    thumbnail_headline: dict = None,
):
    """
    Sprint124 - Thumbnail=First Frame Policy. Imagen으로 별도 썸네일을
    생성하지 않는다 - 이미 렌더링된 영상(video_builder.py의 무음
    합성본, subtitle mux 전)의 첫 프레임을 그대로 추출해 그 위에
    thumbnail_headline만 얹는다. thumbnail_headline이 없으면(생성
    실패 등, 기본값 None) 오버레이 없이 첫 프레임 그대로를 반환한다 -
    예외를 던지지 않는다.

    title/topic/channel/scene1_narration/scene1_image_prompt는 더 이상
    프롬프트 생성에 쓰이지 않지만(과거 Imagen 프롬프트 조립용), 호출
    시그니처를 유지하기 위해 그대로 받는다.
    """

    video_path = os.path.join(
        project_path, "video", silent_video_filename(render_profile),
    )

    output = os.path.join(
        project_path,
        thumbnail_filename(render_profile),
    )

    _extract_first_frame(video_path, output)

    if thumbnail_headline:
        _draw_headline(output, thumbnail_headline)

    return output
