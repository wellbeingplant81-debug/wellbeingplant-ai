"""
Sprint104 - Video Distribution Intelligence.

Upload Queue의 상태 머신을 담당하는 순수 함수 모듈이다(네트워크/파일
I/O 없음 - 저장은 distribution_store.py 소관, 실제 발행은
distribution_service.py/platform_adapter.py 소관).

허용된 상태 전이만 통과시키고, 나머지는 전부 InvalidTransitionError로
막는다 - "모르는 조합은 조용히 무시"하지 않는다.

    generated --submit_for_review--> waiting_review
    waiting_review --approve--> approved
    waiting_review --reject--> rejected
    rejected --re_review--> waiting_review
    approved --cancel--> waiting_review
    approved --publish--> publishing
    failed --publish--> publishing (수동 재시도, 자동 재시도 없음)
    publishing --mark_published--> published
    publishing --mark_failed--> failed

approved 이후에는 필드 직접 수정을 금지한다(§8-3) - can_edit_fields()가
generated/waiting_review/rejected에서만 True를 반환한다. cancel로
approved에서 빠져나와야만 다시 편집 가능한 상태(waiting_review)가 된다.
"""

STATUS_GENERATED = "generated"
STATUS_WAITING_REVIEW = "waiting_review"
STATUS_APPROVED = "approved"
STATUS_PUBLISHING = "publishing"
STATUS_PUBLISHED = "published"
STATUS_FAILED = "failed"
STATUS_REJECTED = "rejected"

ACTION_SUBMIT_FOR_REVIEW = "submit_for_review"
ACTION_APPROVE = "approve"
ACTION_REJECT = "reject"
ACTION_RE_REVIEW = "re_review"
ACTION_CANCEL = "cancel"
ACTION_PUBLISH = "publish"
ACTION_MARK_PUBLISHED = "mark_published"
ACTION_MARK_FAILED = "mark_failed"

_TRANSITIONS = {
    (STATUS_GENERATED, ACTION_SUBMIT_FOR_REVIEW): STATUS_WAITING_REVIEW,
    (STATUS_WAITING_REVIEW, ACTION_APPROVE): STATUS_APPROVED,
    (STATUS_WAITING_REVIEW, ACTION_REJECT): STATUS_REJECTED,
    (STATUS_REJECTED, ACTION_RE_REVIEW): STATUS_WAITING_REVIEW,
    (STATUS_APPROVED, ACTION_CANCEL): STATUS_WAITING_REVIEW,
    (STATUS_APPROVED, ACTION_PUBLISH): STATUS_PUBLISHING,
    (STATUS_FAILED, ACTION_PUBLISH): STATUS_PUBLISHING,
    (STATUS_PUBLISHING, ACTION_MARK_PUBLISHED): STATUS_PUBLISHED,
    (STATUS_PUBLISHING, ACTION_MARK_FAILED): STATUS_FAILED,
}

# generated는 create_entry()가 submit_for_review와 한 호출 안에서 바로
# 통과시키므로 저장소에는 사실상 등장하지 않지만, 방어적으로 편집
# 가능 상태에 포함해둔다.
EDITABLE_STATUSES = {STATUS_GENERATED, STATUS_WAITING_REVIEW, STATUS_REJECTED}


class InvalidTransitionError(Exception):
    pass


def transition(current_status: str, action: str) -> str:
    """
    (current_status, action) 조합이 허용 테이블에 있으면 다음 상태
    문자열을 반환하고, 없으면 InvalidTransitionError를 raise한다.
    상태를 직접 변경하지 않는 순수 함수 - 실제 반영은 호출자(
    distribution_store.apply_action())의 책임이다.
    """

    key = (current_status, action)

    if key not in _TRANSITIONS:
        raise InvalidTransitionError(
            f"Cannot apply action '{action}' to status '{current_status}'"
        )

    return _TRANSITIONS[key]


def can_edit_fields(status: str) -> bool:
    """
    §8-3 - approved 이후(approved/publishing/published/failed)에는
    title/description/hashtags 등 사용자 콘텐츠 필드를 직접 수정할 수
    없다. publish_result처럼 시스템이 기록하는 필드는 이 제한과
    무관하다(distribution_store.apply_action()의 별도 파라미터로 처리).
    """

    return status in EDITABLE_STATUSES
