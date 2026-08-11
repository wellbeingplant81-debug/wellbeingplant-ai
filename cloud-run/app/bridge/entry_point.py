"""AI Bridge 진입점 감싸개 -- `run_pipeline` 앞에 선다.

⚠⚠ **이 제품의 진입점은 영상 한 편을 만드는 일 전체다.** 부르면 대본(LLM) ·
스톡 검색 · 이미지 · TTS · 자막 · 합성 · 썸네일이 실제로 돌고, **마지막이
업로드다**. `pipeline.py` 가 스스로 적는다: *"Sprint92 - 업로드. 반드시
마지막이다 … 갓 만든 프로젝트는 아직 사람이 보지 않았으므로 승인 상태가 아니고,
studio_upload 가 그것을 보고 건너뛴다."* 제품 자신의 관문이 있다는 뜻이지
**업로드 경로가 없다는 뜻이 아니다** -- 이미 승인된 프로젝트 경로를 주면
올라간다.

그래서 이 감싸개에서 가장 중요한 것은 부르는 법이 아니라 **부르지 않는 법**이다.
`ENABLE_REAL_VIDEO_PIPELINE` 이 배송 기본값 `False` 이고, 켜는 코드는 이
저장소에 없다.

**파이프라인을 import 하지 않고 받는다.** 최상단에서 `app.pipeline` 을 import
하면 그것만으로 `requirements.txt` 77줄(`google.genai` · `moviepy` …)이 전부
필요해진다 -- 감싸개를 얹었더니 import 가 무거워지는 일은 하지 않는다.

**세 값을 지어내지 않는다.** `project_path` 를 추측하면 남의 프로젝트 폴더에
쓰고, `channel` 을 추측하면 엉뚱한 채널로 올라간다. 비어 있으면 거절한다.

**돌려받은 것을 해석하지 않는다.** 무엇이 성공인지는 그 파이프라인의 규약이다.
"""

from dataclasses import dataclass

#: 배송 기본값. **켜는 코드는 이 저장소에 없다** -- 부르는 쪽의 결정이다.
ENABLE_REAL_VIDEO_PIPELINE = False

STATUS_SUCCEEDED = "SUCCEEDED"
#: 돌려보지 않았다. **실패가 아니고, 막힌 것도 아니다.**
STATUS_NEVER_RAN = "NEVER_RAN"
#: 관문이 막았다 -- 부를 수 없었다.
STATUS_BLOCKED = "BLOCKED"
#: 불렀고 실패했다.
STATUS_FAILED = "FAILED"

_FLAG_OFF = (
    "ENABLE_REAL_VIDEO_PIPELINE 이 꺼져 있어 파이프라인을 부르지 않았다 -- "
    "실패한 것이 아니라 돌려보지 않은 것이다"
)
_NO_PIPELINE = (
    "부를 파이프라인이 주입되지 않았다 -- 여기서 import 하지 않는다"
    "(import 만으로 requirements 77줄이 필요해진다)"
)
_MISSING = "{field} 가 비어 있다 -- 기본값을 지어내지 않는다(추측하면 엉뚱한 곳에 만들고 올린다)"
_NOT_A_REQUEST = "VideoRequest 가 아니다 -- 요청을 해석하거나 고쳐 쓰지 않는다"

_REQUIRED = ("topic", "project_path", "channel")


@dataclass(frozen=True)
class VideoRequest:
    """영상 하나를 만들라는 요청. **세 값 다 선언되어야 한다.**"""

    topic: str
    project_path: str
    channel: str


@dataclass(frozen=True)
class VideoResponse:
    """부르려 한 결과. **부르지 않은 것도 결과다.**"""

    status: str
    topic: str
    #: 파이프라인이 돌려준 것. **해석하지 않고 그대로 나른다.**
    value: object = None
    reasons: tuple = ()


class VideoEntryPoint:
    """Bridge 의 `ProductEntryPoint` 를 **구조적으로** 만족한다.

    상속하지 않는 이유는 계약이 `Protocol` 이기 때문이고, 상속하려면
    `ai_bridge` 를 import 해야 하는데 이 저장소는 그것을 쓰지 않기 때문이다.
    """

    def __init__(self, pipeline=None):
        self._pipeline = pipeline

    def execute(self, request):
        if not isinstance(request, VideoRequest):
            # 조용히 BLOCKED 로 접지 않는다 -- "거절했다" 와 "잘못 불렀다" 는
            # 다른 사실이다. 예외를 다루는 것은 Bridge 쪽 Activation 의 일이다.
            raise TypeError(_NOT_A_REQUEST)

        topic = request.topic

        def _refused(why):
            return VideoResponse(status=STATUS_BLOCKED, topic=topic, reasons=(why,))

        if not ENABLE_REAL_VIDEO_PIPELINE:
            return VideoResponse(
                status=STATUS_NEVER_RAN, topic=topic, reasons=(_FLAG_OFF,)
            )

        if self._pipeline is None:
            return _refused(_NO_PIPELINE)

        for field in _REQUIRED:
            if not str(getattr(request, field, "")).strip():
                return _refused(_MISSING.format(field=field))

        try:
            value = self._pipeline(
                topic=request.topic,
                project_path=request.project_path,
                channel=request.channel,
            )
        except Exception as exc:  # noqa: BLE001 -- 되살리지 않는다. 실패도 결과다.
            return VideoResponse(
                status=STATUS_FAILED,
                topic=topic,
                reasons=("{0}: {1}".format(type(exc).__name__, exc),),
            )

        return VideoResponse(status=STATUS_SUCCEEDED, topic=topic, value=value)
