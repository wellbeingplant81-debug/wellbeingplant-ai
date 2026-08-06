"""
AI Factory 2.0, Part 4/5 - Publishing Plan Model.

Job 하나가 (언젠가) 어떻게 게시될지에 대한 순수 계획 데이터다 - 실제
Upload를 절대 하지 않는다("자동 게시 금지", "YouTube API 추가 금지").
Published 상태조차 "실제로 올라갔다"가 아니라 "예약 상태로 표시했다"는
뜻이다(Part 5 - "Published(예약 상태만)").

Campaign(campaign_model.py)과 동일한 스타일의 평면 dataclass다 - 전부
str/list/float라 dataclasses.asdict()/PublishingPlan(**dict)로 그대로
JSON 직렬화된다.

AI Factory 3.0, Part 1/3/4/5 - Connector 연동을 위한 필드 추가.
"Publishing"(Connector에 제출됐지만 아직 결과가 확정되지 않은 상태)이
Status에 추가됐다 - 지금의 MockConnector는 동기적으로 즉시 응답하므로
실제로 관측되는 시간은 짧지만, 나중에 실제(비동기) Connector가 생기면
이 상태가 의미 있게 오래 유지될 수 있다. external_id/last_message/
retryable은 ConnectorResult(connectors/connector_result.py)를 그대로
옮겨 담을 뿐, 새로 계산하는 값이 아니다.

AI Factory 3.1, Part 2 - output_folder 추가. YouTubeConnector가 실제
업로드할 영상 파일(project_path/video/final_short.mp4 등) 위치를 알아야
하는데, 이전까지는 이 정보가 Plan에 저장돼 있지 않았다(publishing_plan_
service.build_publishing_plan()이 publish_package.json을 읽을 때만
잠깐 썼을 뿐, 결과 Plan 객체에는 남기지 않았다) - 기존 Plan과 100%
호환(기본값 빈 문자열)되는 추가 필드다.

AI Factory 4.0, Part 1 - scheduled_at/schedule_state 추가(Scheduler
Foundation). status(Planned/Ready/Publishing/Published/Failed)와는
완전히 별개의 축이다 - status는 "이 Plan이 실제로 게시 가능한 상태인가"
를, schedule_state는 "이 Plan에 걸린 예약이 지금 어떤 단계인가"를
나타낸다. schedule_state 기본값 "READY"는 "아직 예약이 걸리지 않음"을
뜻한다(PublishingController.schedule_plan()이 호출되기 전까지는 이
값 그대로 남는다) - "Ready"(status)와 철자만 같을 뿐 다른 축의 값이다.
scheduled_at은 다른 시간 필드(publish_time/created_at/updated_at)와
동일하게 Unix Timestamp(float)로 저장한다 - 새 시간 표현 방식을
만들지 않는다. 둘 다 기존 Plan과 100% 호환(로드 시 키가 없으면 그냥
기본값)된다(publishing_plan_store.load_publishing_plans()가 이미
dataclass 기본값에 의존하는 방식이라 추가 마이그레이션이 필요 없다).
"""

import time
import uuid
from dataclasses import dataclass, field
from typing import Optional

STATUS_OPTIONS = [
    "Planned", "Ready", "Publishing", "Published", "Failed",
    # Phase 5, Epic (Priority 3) - 자동 재시도가 소진됐거나(retry_count가
    # 한도 도달) 애초에 자동 재시도 대상이 아닌(OAuth/Permission/
    # Validation/Caption/Policy 등) 실패의 최종 상태. 여기서부터는
    # 사용자가 "다시 시도" 버튼(PublishingController.retry_plan())으로만
    # 재시도할 수 있다 - 자동 재시도는 다시는 이 Plan을 건드리지 않는다
    # (무한 루프 방지의 핵심 경계).
    "FAILED_REQUIRES_USER",
    # Priority 3 UI - Publishing Queue 화면의 "취소" 버튼(PublishingController.
    # cancel_plan())이 만드는 최종 상태다. Failed/FAILED_REQUIRES_USER
    # Plan을 더 이상 다루지 않기로 사람이 명시적으로 결정했다는 뜻 -
    # Retry Queue/Dead Letter Queue 어느 쪽에도 다시 나타나지 않는다.
    "Cancelled",
]
DEFAULT_STATUS = "Planned"
SCHEDULE_STATE_OPTIONS = ["READY", "WAITING", "RUNNING", "COMPLETED", "FAILED"]
DEFAULT_SCHEDULE_STATE = "READY"


@dataclass
class PublishingPlan:

    job_id: str
    campaign_id: str = ""
    platform: str = ""
    title: str = ""
    description: str = ""
    hashtags: list = field(default_factory=list)
    output_folder: str = ""
    publish_time: Optional[float] = None
    status: str = DEFAULT_STATUS
    external_id: str = ""
    last_message: str = ""
    retryable: bool = False
    plan_id: str = ""
    created_at: float = 0.0
    updated_at: float = 0.0
    scheduled_at: Optional[float] = None
    schedule_state: str = DEFAULT_SCHEDULE_STATE
    dry_run: bool = False
    pipeline_trace: list = field(default_factory=list)
    retry_count: int = 0
    # Phase 5, Epic (Priority 3) - 자동 재시도 적격 여부/대기 시간 계산에
    # 쓰인다. error_category는 ConnectorResult.error_category(이미
    # real_instagram_runtime.py가 실제 HTTP 상태로 계산해 두는 값)를
    # 그대로 옮겨 담을 뿐이다 - 새 판정 로직 없음. retry_after_seconds는
    # HTTP 429 응답의 Retry-After 헤더 값이다(없으면 None).
    error_category: str = ""
    retry_after_seconds: Optional[float] = None

    def __post_init__(self) -> None:
        if not self.plan_id:
            self.plan_id = str(uuid.uuid4())
        if not self.created_at:
            self.created_at = time.time()
        if not self.updated_at:
            self.updated_at = self.created_at
