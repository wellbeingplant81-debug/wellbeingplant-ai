"""
Sprint104 - Video Distribution Intelligence. distribution_store.py는
Upload Queue를 JSON 파일 하나(video_id를 key로 하는 dict)에 영속화하는
계층이다 - asset_feedback_service.py와 동일한 컨벤션(경로 파라미터로
테스트 시 tmp 경로 오버라이드, atomic_write_json으로 저장, 파일이
없거나 손상돼도 예외 없이 빈 상태로 처리).

상태 전이(transition/can_edit_fields)는 distribution_queue.py 소관이고,
이 모듈은 그 결과를 실제로 디스크에 쓰고 읽는 것만 담당한다.
"""

import json
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.services import distribution_queue as dq
from app.services import distribution_store


class TestDistributionStoreBase(unittest.TestCase):

    def setUp(self):
        self._tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp_dir.cleanup)
        self.queue_path = os.path.join(self._tmp_dir.name, "distribution_queue.json")

    def _create_sample_entry(self, video_id="20260715_120000", **overrides):
        kwargs = dict(
            video_id=video_id,
            output_path=f"output/{video_id}",
            title="제목",
            description="설명",
            hashtags=["health", "shorts"],
            thumbnail_path=f"output/{video_id}/thumbnail.png",
            target_platforms=["youtube"],
            publish_mode="immediate",
            queue_path=self.queue_path,
        )
        kwargs.update(overrides)
        return distribution_store.create_entry(**kwargs)


class TestCreateEntry(TestDistributionStoreBase):

    def test_create_entry_lands_on_waiting_review(self):
        # SPEC: "(explicit API) -> generated -> waiting_review (즉시,
        # 같은 호출 내에서)" - 저장된 최종 상태는 waiting_review여야
        # 한다.
        entry = self._create_sample_entry()
        self.assertEqual(entry["status"], dq.STATUS_WAITING_REVIEW)

    def test_create_entry_persists_to_disk(self):
        self._create_sample_entry(video_id="v1")

        with open(self.queue_path, encoding="utf-8") as f:
            saved = json.load(f)

        self.assertIn("v1", saved)
        self.assertEqual(saved["v1"]["status"], dq.STATUS_WAITING_REVIEW)

    def test_create_entry_uses_atomic_write_json(self):
        with patch(
            "app.services.distribution_store.atomic_write_json",
        ) as mock_write:
            self._create_sample_entry(video_id="v1")
            mock_write.assert_called_once()
            called_path = mock_write.call_args.args[0]
            self.assertEqual(called_path, self.queue_path)

    def test_video_id_reused_as_key_not_a_new_id_scheme(self):
        entry = self._create_sample_entry(video_id="20260715_120000")
        self.assertEqual(entry["video_id"], "20260715_120000")

    def test_all_spec_fields_present(self):
        entry = self._create_sample_entry()
        for field in [
            "video_id", "output_path", "title", "description", "hashtags",
            "thumbnail_path", "target_platforms", "publish_mode",
            "scheduled_at", "status", "created_at", "updated_at",
            "publish_result",
        ]:
            with self.subTest(field=field):
                self.assertIn(field, entry)

    def test_publish_result_starts_as_none(self):
        entry = self._create_sample_entry()
        self.assertIsNone(entry["publish_result"])


class TestGetAndListEntries(TestDistributionStoreBase):

    def test_get_entry_returns_none_when_missing(self):
        self.assertIsNone(
            distribution_store.get_entry("nope", queue_path=self.queue_path)
        )

    def test_get_entry_returns_created_entry(self):
        self._create_sample_entry(video_id="v1")
        entry = distribution_store.get_entry("v1", queue_path=self.queue_path)
        self.assertEqual(entry["video_id"], "v1")

    def test_list_entries_empty_when_file_missing(self):
        self.assertEqual(
            distribution_store.list_entries(queue_path=self.queue_path), []
        )

    def test_list_entries_returns_all(self):
        self._create_sample_entry(video_id="v1")
        self._create_sample_entry(video_id="v2")
        entries = distribution_store.list_entries(queue_path=self.queue_path)
        self.assertEqual({e["video_id"] for e in entries}, {"v1", "v2"})

    def test_list_entries_filters_by_status(self):
        self._create_sample_entry(video_id="v1")
        self._create_sample_entry(video_id="v2")
        distribution_store.apply_action(
            "v1", dq.ACTION_APPROVE, queue_path=self.queue_path,
        )

        approved = distribution_store.list_entries(
            status=dq.STATUS_APPROVED, queue_path=self.queue_path,
        )
        waiting = distribution_store.list_entries(
            status=dq.STATUS_WAITING_REVIEW, queue_path=self.queue_path,
        )

        self.assertEqual([e["video_id"] for e in approved], ["v1"])
        self.assertEqual([e["video_id"] for e in waiting], ["v2"])

    def test_corrupted_file_treated_as_empty(self):
        os.makedirs(os.path.dirname(self.queue_path), exist_ok=True)
        with open(self.queue_path, "w", encoding="utf-8") as f:
            f.write("{not valid json")

        self.assertEqual(
            distribution_store.list_entries(queue_path=self.queue_path), []
        )


class TestApplyAction(TestDistributionStoreBase):

    def test_apply_action_transitions_status(self):
        self._create_sample_entry(video_id="v1")

        updated = distribution_store.apply_action(
            "v1", dq.ACTION_APPROVE, queue_path=self.queue_path,
        )

        self.assertEqual(updated["status"], dq.STATUS_APPROVED)

    def test_apply_action_persists_new_status(self):
        self._create_sample_entry(video_id="v1")
        distribution_store.apply_action(
            "v1", dq.ACTION_APPROVE, queue_path=self.queue_path,
        )

        reloaded = distribution_store.get_entry("v1", queue_path=self.queue_path)
        self.assertEqual(reloaded["status"], dq.STATUS_APPROVED)

    def test_apply_action_updates_updated_at(self):
        entry = self._create_sample_entry(video_id="v1")
        original_updated_at = entry["updated_at"]

        updated = distribution_store.apply_action(
            "v1", dq.ACTION_APPROVE, queue_path=self.queue_path,
        )

        self.assertNotEqual(updated["updated_at"], "")
        self.assertIsNotNone(updated["updated_at"])
        # created_at은 절대 바뀌지 않는다.
        self.assertEqual(updated["created_at"], entry["created_at"])

    def test_apply_action_raises_for_missing_entry(self):
        with self.assertRaises(distribution_store.EntryNotFoundError):
            distribution_store.apply_action(
                "missing", dq.ACTION_APPROVE, queue_path=self.queue_path,
            )

    def test_apply_action_raises_for_invalid_transition(self):
        self._create_sample_entry(video_id="v1")  # -> waiting_review

        with self.assertRaises(dq.InvalidTransitionError):
            # waiting_review에서 바로 publish는 금지(approve를 거쳐야 함)
            distribution_store.apply_action(
                "v1", dq.ACTION_PUBLISH, queue_path=self.queue_path,
            )

    def test_invalid_transition_does_not_mutate_stored_status(self):
        self._create_sample_entry(video_id="v1")

        try:
            distribution_store.apply_action(
                "v1", dq.ACTION_PUBLISH, queue_path=self.queue_path,
            )
        except dq.InvalidTransitionError:
            pass

        reloaded = distribution_store.get_entry("v1", queue_path=self.queue_path)
        self.assertEqual(reloaded["status"], dq.STATUS_WAITING_REVIEW)

    def test_approve_allows_field_overrides(self):
        self._create_sample_entry(video_id="v1", title="원래 제목")

        updated = distribution_store.apply_action(
            "v1", dq.ACTION_APPROVE,
            field_overrides={"title": "수정된 제목"},
            queue_path=self.queue_path,
        )

        self.assertEqual(updated["title"], "수정된 제목")
        self.assertEqual(updated["status"], dq.STATUS_APPROVED)

    def test_cancel_with_field_overrides_is_rejected(self):
        # §8-3: approved 상태에서는 필드 직접 수정 금지. cancel은
        # approved에서 호출되므로(전이 전 상태 기준) field_overrides를
        # 실어 보내면 거부돼야 한다.
        self._create_sample_entry(video_id="v1")
        distribution_store.apply_action(
            "v1", dq.ACTION_APPROVE, queue_path=self.queue_path,
        )

        with self.assertRaises(distribution_store.FieldEditNotAllowedError):
            distribution_store.apply_action(
                "v1", dq.ACTION_CANCEL,
                field_overrides={"title": "몰래 수정"},
                queue_path=self.queue_path,
            )

    def test_mark_published_can_set_publish_result_without_field_edit_error(self):
        # publish_result는 시스템이 기록하는 값이라 can_edit_fields()의
        # "사용자 콘텐츠 필드 잠금" 대상이 아니다 - publishing 상태에서도
        # 항상 기록 가능해야 한다.
        self._create_sample_entry(video_id="v1")
        distribution_store.apply_action(
            "v1", dq.ACTION_APPROVE, queue_path=self.queue_path,
        )
        distribution_store.apply_action(
            "v1", dq.ACTION_PUBLISH, queue_path=self.queue_path,
        )

        updated = distribution_store.apply_action(
            "v1", dq.ACTION_MARK_PUBLISHED,
            publish_result={"youtube": {"success": True, "platform_post_id": "mock_1"}},
            queue_path=self.queue_path,
        )

        self.assertEqual(updated["status"], dq.STATUS_PUBLISHED)
        self.assertEqual(
            updated["publish_result"]["youtube"]["platform_post_id"], "mock_1",
        )

    def test_full_reject_re_review_cycle(self):
        self._create_sample_entry(video_id="v1")

        rejected = distribution_store.apply_action(
            "v1", dq.ACTION_REJECT, queue_path=self.queue_path,
        )
        self.assertEqual(rejected["status"], dq.STATUS_REJECTED)

        back = distribution_store.apply_action(
            "v1", dq.ACTION_RE_REVIEW, queue_path=self.queue_path,
        )
        self.assertEqual(back["status"], dq.STATUS_WAITING_REVIEW)

    def test_failed_manual_retry_via_publish(self):
        self._create_sample_entry(video_id="v1")
        distribution_store.apply_action(
            "v1", dq.ACTION_APPROVE, queue_path=self.queue_path,
        )
        distribution_store.apply_action(
            "v1", dq.ACTION_PUBLISH, queue_path=self.queue_path,
        )
        distribution_store.apply_action(
            "v1", dq.ACTION_MARK_FAILED,
            publish_result={"youtube": {"success": False, "error": "boom"}},
            queue_path=self.queue_path,
        )

        retried = distribution_store.apply_action(
            "v1", dq.ACTION_PUBLISH, queue_path=self.queue_path,
        )
        self.assertEqual(retried["status"], dq.STATUS_PUBLISHING)


if __name__ == "__main__":
    unittest.main()
