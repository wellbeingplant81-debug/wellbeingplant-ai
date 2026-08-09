"""
Sprint182 - 문의할 때 그대로 보낼 것 (Epic 59, Phase 5).

Sprint181이 문제와 해결 방법을 만들어 줬다. 그런데 그것을 우리에게
보낼 때, 사람은 어느 화면의 무엇을 긁어야 하는지 또 골라야 했다.

한 덩이로 만든다. 누르면 복사되고, 붙여넣으면 우리가 읽는다.

경로를 담지 않는다
------------------
Sprint174의 [정보 복사]와 다른 자리다. 그쪽은 주인이 제 PC를 들여다
보는 글이라 내 것 자리와 도구 경로가 그대로 들어간다 - 그 사람의
화면에서 그 사람이 읽는 글이다.

이것은 밖으로 나가는 글이다. 그래서 도구는 "있다/없다"만 적는다.
media_tools.available()이 돌려주는 것은 경로이므로, 그대로 담으면
남의 PC 구조가 함께 나간다. bool로 바꾸는 자리가 여기다.

새로 판정하지 않는다
--------------------
    app_info           판번호
    troubleshooting    지금 어디에 있고 무엇이 문제이고 어떻게 하는가
    beta_telemetry     마지막에 무엇을 했는가
    media_tools        도구가 있는가
    runtime_paths      배경 음악이 있는가

여기서 상태를 다시 세면 받아 보는 우리가 화면과 다른 것을 읽게 된다.

아무것도 적지 않는다
--------------------
만들기만 하고 남기지 않는다.
"""

# 리포트에 들어가는 것 전부. 여기 없는 것은 담지 않는다.
FIELDS = (
    "version",
    "current_state",
    "last_action",
    "problem_count",
    "problems",
    "suggestions",
    "environment",
    "report",
)


def _environment() -> dict:
    """
    무엇이 갖춰져 있는가. 있다/없다만 적는다.

    어디 있는지는 적지 않는다 - 이 글은 밖으로 나간다.
    """

    from app import runtime_paths
    from app.services import media_tools

    tools = media_tools.available()

    return {
        media_tools.FFMPEG: bool(tools.get(media_tools.FFMPEG)),
        media_tools.FFPROBE: bool(tools.get(media_tools.FFPROBE)),
        "music": bool(runtime_paths._has_music(runtime_paths.music_root())),
        "packaged": bool(runtime_paths.is_frozen()),
    }


def _text(found: dict) -> str:
    """
    붙여 넣을 글. 서버가 짓는다.

    화면이 제 나름대로 조립하면 받아 보는 글의 모양이 사람마다 달라
    무엇이 빠졌는지 알 수 없다(Sprint174에서 정한 규칙).
    """

    from app import app_info

    lines = [
        f"{app_info.NAME} 진단 정보",
        "",
        f"버전        {found['version']}",
        f"현재 단계   {found['current_state']}",
        f"마지막 상태 {found['last_action'] or '아직 없음'}",
        f"문제        {found['problem_count']}건",
        "",
        "갖춰진 것",
    ]

    for name, there in found["environment"].items():
        lines.append(f"  {name:<10} {'있음' if there else '없음'}")

    if found["problems"]:
        lines += ["", "문제"]
        lines += [f"  - {line}" for line in found["problems"]]

    if found["suggestions"]:
        lines += ["", "해결 방법"]
        lines += [f"  - {line}" for line in found["suggestions"]]

    lines += ["", f"보내실 곳: {app_info.CONTACT}"]

    return "\n".join(lines)


def build(store_path: str, project_path: str = None) -> dict:
    """
    문의용 한 덩이. 읽기만 한다.

    상태·문제·해결 방법은 troubleshooting이 낸 그대로다 - 여기서
    다시 세면 화면과 다른 말을 하게 된다.
    """

    from app import app_info
    from app.services import beta_telemetry, troubleshooting

    told = troubleshooting.build(store_path, project_path)
    usage = beta_telemetry.summary()

    found = {
        "version": app_info.VERSION,
        "current_state": told["status"],
        "last_action": usage.get("last_event"),
        "problem_count": len(told["problems"]),
        "problems": list(told["problems"]),
        "suggestions": list(told["suggestions"]),
        "environment": _environment(),
    }

    found["report"] = _text(found)

    return found
