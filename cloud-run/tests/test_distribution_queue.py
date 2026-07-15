"""
Sprint104 - Video Distribution Intelligence. distribution_queue.py는
Upload Queue의 상태 머신을 담당하는 순수 함수 모듈이다(네트워크/파일
I/O 없음 - 저장은 distribution_store.py 소관).

SPEC에서 확정한 상태 전이만 허용한다:

    generated --submit_for_review--> waiting_review
    waiting_review --approve--> approved
    waiting_review --reject--> rejected
    rejected --re_review--> waiting_review
    approved --cancel--> waiting_review
    approved --publish--> publishing
    failed --publish--> publishing (수동 재시도)
    publishing --mark_published--> published
    publishing --mark_failed--> failed

approved 상태에서는 필드 직접 수정이 금지된다(§8-3) - can_edit_fields()는
generated/waiting_review/rejected에서만 True.
"""

import os
import sys
import unittest

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.services import distribution_queue as dq


class TestAllowedTransitions(unittest.TestCase):

    def test_generated_to_waiting_review(self):
        self.assertEqual(
            dq.transition(dq.STATUS_GENERATED, dq.ACTION_SUBMIT_FOR_REVIEW),
            dq.STATUS_WAITING_REVIEW,
        )

    def test_waiting_review_to_approved(self):
        self.assertEqual(
            dq.transition(dq.STATUS_WAITING_REVIEW, dq.ACTION_APPROVE),
            dq.STATUS_APPROVED,
        )

    def test_waiting_review_to_rejected(self):
        self.assertEqual(
            dq.transition(dq.STATUS_WAITING_REVIEW, dq.ACTION_REJECT),
            dq.STATUS_REJECTED,
        )

    def test_rejected_to_waiting_review_via_re_review(self):
        self.assertEqual(
            dq.transition(dq.STATUS_REJECTED, dq.ACTION_RE_REVIEW),
            dq.STATUS_WAITING_REVIEW,
        )

    def test_approved_to_waiting_review_via_cancel(self):
        self.assertEqual(
            dq.transition(dq.STATUS_APPROVED, dq.ACTION_CANCEL),
            dq.STATUS_WAITING_REVIEW,
        )

    def test_approved_to_publishing(self):
        self.assertEqual(
            dq.transition(dq.STATUS_APPROVED, dq.ACTION_PUBLISH),
            dq.STATUS_PUBLISHING,
        )

    def test_failed_to_publishing_manual_retry(self):
        self.assertEqual(
            dq.transition(dq.STATUS_FAILED, dq.ACTION_PUBLISH),
            dq.STATUS_PUBLISHING,
        )

    def test_publishing_to_published(self):
        self.assertEqual(
            dq.transition(dq.STATUS_PUBLISHING, dq.ACTION_MARK_PUBLISHED),
            dq.STATUS_PUBLISHED,
        )

    def test_publishing_to_failed(self):
        self.assertEqual(
            dq.transition(dq.STATUS_PUBLISHING, dq.ACTION_MARK_FAILED),
            dq.STATUS_FAILED,
        )


class TestForbiddenTransitions(unittest.TestCase):
    """
    허용 테이블에 없는 (status, action) 조합은 전부
    InvalidTransitionError를 raise해야 한다 - 상태를 바꾸지 않고 그냥
    무시하는 것은 허용하지 않는다(호출자가 실수로 잘못된 액션을 보냈을
    때 조용히 넘어가면 안 됨).
    """

    def test_waiting_review_cannot_publish_directly(self):
        # approve를 거치지 않고 바로 publish 시도 - 반드시 막혀야 한다.
        with self.assertRaises(dq.InvalidTransitionError):
            dq.transition(dq.STATUS_WAITING_REVIEW, dq.ACTION_PUBLISH)

    def test_generated_cannot_approve_directly(self):
        with self.assertRaises(dq.InvalidTransitionError):
            dq.transition(dq.STATUS_GENERATED, dq.ACTION_APPROVE)

    def test_approved_cannot_be_approved_again(self):
        with self.assertRaises(dq.InvalidTransitionError):
            dq.transition(dq.STATUS_APPROVED, dq.ACTION_APPROVE)

    def test_rejected_cannot_approve_directly_without_re_review(self):
        # rejected -> approved는 존재하지 않는다. 반드시 re_review로
        # waiting_review를 거쳐야 한다.
        with self.assertRaises(dq.InvalidTransitionError):
            dq.transition(dq.STATUS_REJECTED, dq.ACTION_APPROVE)

    def test_waiting_review_cannot_cancel(self):
        # cancel은 approved 전용이다.
        with self.assertRaises(dq.InvalidTransitionError):
            dq.transition(dq.STATUS_WAITING_REVIEW, dq.ACTION_CANCEL)

    def test_published_is_terminal(self):
        for action in [
            dq.ACTION_APPROVE, dq.ACTION_REJECT, dq.ACTION_RE_REVIEW,
            dq.ACTION_CANCEL, dq.ACTION_PUBLISH, dq.ACTION_MARK_PUBLISHED,
            dq.ACTION_MARK_FAILED, dq.ACTION_SUBMIT_FOR_REVIEW,
        ]:
            with self.subTest(action=action):
                with self.assertRaises(dq.InvalidTransitionError):
                    dq.transition(dq.STATUS_PUBLISHED, action)

    def test_publishing_cannot_be_interrupted(self):
        # publishing 중에는 approve/reject/cancel 전부 막혀야 한다 -
        # 진행 중인 발행을 리뷰 액션이 끼어들어 상태를 바꾸면 안 된다.
        for action in [dq.ACTION_APPROVE, dq.ACTION_REJECT, dq.ACTION_CANCEL]:
            with self.subTest(action=action):
                with self.assertRaises(dq.InvalidTransitionError):
                    dq.transition(dq.STATUS_PUBLISHING, action)

    def test_failed_cannot_approve_directly(self):
        # failed에서 재시도는 publish 액션 하나뿐이다.
        with self.assertRaises(dq.InvalidTransitionError):
            dq.transition(dq.STATUS_FAILED, dq.ACTION_APPROVE)

    def test_unknown_status_raises(self):
        with self.assertRaises(dq.InvalidTransitionError):
            dq.transition("not_a_real_status", dq.ACTION_APPROVE)


class TestCanEditFields(unittest.TestCase):
    """§8-3 - approved 이후에는 필드 직접 수정 금지."""

    def test_editable_statuses(self):
        for status in [
            dq.STATUS_GENERATED, dq.STATUS_WAITING_REVIEW, dq.STATUS_REJECTED,
        ]:
            with self.subTest(status=status):
                self.assertTrue(dq.can_edit_fields(status))

    def test_non_editable_statuses(self):
        for status in [
            dq.STATUS_APPROVED, dq.STATUS_PUBLISHING, dq.STATUS_PUBLISHED,
            dq.STATUS_FAILED,
        ]:
            with self.subTest(status=status):
                self.assertFalse(dq.can_edit_fields(status))


if __name__ == "__main__":
    unittest.main()
