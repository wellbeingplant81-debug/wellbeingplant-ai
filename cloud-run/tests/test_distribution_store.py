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


class TestDuplicateEnqueuePrevention(TestDistributionStoreBase):
    """
    Sprint105 §7 - 동일 video_id로 create_entry()를 두 번 호출하면
    기존 항목(어떤 상태든, 예: approved까지 진행된 항목)을 조용히
    덮어쓰는 대신 DuplicateEntryError를 raise한다.
    """

    def test_duplicate_video_id_raises(self):
        self._create_sample_entry(video_id="v1")

        with self.assertRaises(distribution_store.DuplicateEntryError):
            self._create_sample_entry(video_id="v1")

    def test_duplicate_attempt_does_not_overwrite_existing_entry(self):
        self._create_sample_entry(video_id="v1", title="원본 제목")
        distribution_store.apply_action(
            "v1", dq.ACTION_APPROVE, queue_path=self.queue_path,
        )

        try:
            self._create_sample_entry(video_id="v1", title="덮어쓰기 시도")
        except distribution_store.DuplicateEntryError:
            pass

        entry = distribution_store.get_entry("v1", queue_path=self.queue_path)
        self.assertEqual(entry["title"], "원본 제목")
        self.assertEqual(entry["status"], dq.STATUS_APPROVED)

    def test_different_video_ids_do_not_collide(self):
        self._create_sample_entry(video_id="v1")
        self._create_sample_entry(video_id="v2")  # 예외 없이 통과해야 함

        self.assertEqual(
            len(distribution_store.list_entries(queue_path=self.queue_path)), 2,
        )


class TestReviewMetadataSnapshot(TestDistributionStoreBase):
    """
    Sprint105 §5 - Pipeline을 직접 조회하지 않고, enqueue 호출자가
    넘긴 값을 그대로 저장하는 snapshot 필드. thumbnail_preview는
    §8-1 결정에 따라 추가하지 않고 기존 thumbnail_path를 재사용한다.
    """

    def test_snapshot_fields_are_stored_when_provided(self):
        entry = self._create_sample_entry(
            video_id="v1",
            video_duration=45.2,
            quality_score=0.91,
            generation_time=132.5,
            source_project="output/20260715_120000",
        )

        self.assertEqual(entry["video_duration"], 45.2)
        self.assertEqual(entry["quality_score"], 0.91)
        self.assertEqual(entry["generation_time"], 132.5)
        self.assertEqual(entry["source_project"], "output/20260715_120000")

    def test_snapshot_fields_default_to_none_when_omitted(self):
        entry = self._create_sample_entry(video_id="v1")

        for field in [
            "video_duration", "quality_score", "generation_time", "source_project",
        ]:
            with self.subTest(field=field):
                self.assertIsNone(entry[field])

    def test_no_thumbnail_preview_field_exists(self):
        # §8-1 확정 - thumbnail_preview는 신규 필드로 추가하지 않는다.
        entry = self._create_sample_entry(video_id="v1")
        self.assertNotIn("thumbnail_preview", entry)


class TestDashboardStats(TestDistributionStoreBase):

    def test_empty_queue_all_zero(self):
        stats = distribution_store.get_dashboard_stats(queue_path=self.queue_path)

        self.assertEqual(stats["total"], 0)
        for status in [
            dq.STATUS_GENERATED, dq.STATUS_WAITING_REVIEW, dq.STATUS_APPROVED,
            dq.STATUS_PUBLISHING, dq.STATUS_PUBLISHED, dq.STATUS_FAILED,
            dq.STATUS_REJECTED,
        ]:
            with self.subTest(status=status):
                self.assertEqual(stats[status], 0)

    def test_counts_reflect_actual_statuses(self):
        self._create_sample_entry(video_id="v1")  # waiting_review
        self._create_sample_entry(video_id="v2")  # waiting_review
        distribution_store.apply_action(
            "v2", dq.ACTION_APPROVE, queue_path=self.queue_path,
        )
        self._create_sample_entry(video_id="v3")
        distribution_store.apply_action(
            "v3", dq.ACTION_REJECT, queue_path=self.queue_path,
        )

        stats = distribution_store.get_dashboard_stats(queue_path=self.queue_path)

        self.assertEqual(stats["total"], 3)
        self.assertEqual(stats[dq.STATUS_WAITING_REVIEW], 1)
        self.assertEqual(stats[dq.STATUS_APPROVED], 1)
        self.assertEqual(stats[dq.STATUS_REJECTED], 1)


class TestQueueFilteringExtended(TestDistributionStoreBase):

    def test_filter_by_platform(self):
        self._create_sample_entry(video_id="v1", target_platforms=["youtube"])
        self._create_sample_entry(video_id="v2", target_platforms=["instagram"])
        self._create_sample_entry(
            video_id="v3", target_platforms=["youtube", "tiktok"],
        )

        youtube_entries = distribution_store.list_entries(
            platform="youtube", queue_path=self.queue_path,
        )

        self.assertEqual(
            {e["video_id"] for e in youtube_entries}, {"v1", "v3"},
        )

    def test_filter_by_publish_mode(self):
        self._create_sample_entry(video_id="v1", publish_mode="immediate")
        self._create_sample_entry(video_id="v2", publish_mode="scheduled")

        scheduled = distribution_store.list_entries(
            publish_mode="scheduled", queue_path=self.queue_path,
        )

        self.assertEqual([e["video_id"] for e in scheduled], ["v2"])

    def test_filters_combine_with_and_semantics(self):
        self._create_sample_entry(
            video_id="v1", target_platforms=["youtube"], publish_mode="immediate",
        )
        self._create_sample_entry(
            video_id="v2", target_platforms=["youtube"], publish_mode="scheduled",
        )

        result = distribution_store.list_entries(
            platform="youtube", publish_mode="scheduled", queue_path=self.queue_path,
        )

        self.assertEqual([e["video_id"] for e in result], ["v2"])

    def test_status_and_platform_filters_combine(self):
        self._create_sample_entry(video_id="v1", target_platforms=["youtube"])
        self._create_sample_entry(video_id="v2", target_platforms=["youtube"])
        distribution_store.apply_action(
            "v2", dq.ACTION_APPROVE, queue_path=self.queue_path,
        )

        result = distribution_store.list_entries(
            status=dq.STATUS_APPROVED, platform="youtube", queue_path=self.queue_path,
        )

        self.assertEqual([e["video_id"] for e in result], ["v2"])


class TestRetryCountTracking(TestDistributionStoreBase):
    """Sprint105 §6 - retry_count는 failed에서 publish로 재시도할 때만 증가한다."""

    def test_new_entry_starts_at_zero(self):
        entry = self._create_sample_entry(video_id="v1")
        self.assertEqual(entry["retry_count"], 0)

    def test_first_publish_attempt_does_not_increment(self):
        self._create_sample_entry(video_id="v1")
        distribution_store.apply_action(
            "v1", dq.ACTION_APPROVE, queue_path=self.queue_path,
        )
        entry = distribution_store.apply_action(
            "v1", dq.ACTION_PUBLISH, queue_path=self.queue_path,
        )
        self.assertEqual(entry["retry_count"], 0)

    def test_retry_after_failure_increments(self):
        self._create_sample_entry(video_id="v1")
        distribution_store.apply_action(
            "v1", dq.ACTION_APPROVE, queue_path=self.queue_path,
        )
        distribution_store.apply_action(
            "v1", dq.ACTION_PUBLISH, queue_path=self.queue_path,
        )
        distribution_store.apply_action(
            "v1", dq.ACTION_MARK_FAILED, queue_path=self.queue_path,
        )

        retried = distribution_store.apply_action(
            "v1", dq.ACTION_PUBLISH, queue_path=self.queue_path,
        )
        self.assertEqual(retried["retry_count"], 1)

    def test_multiple_retries_increment_each_time(self):
        self._create_sample_entry(video_id="v1")
        distribution_store.apply_action(
            "v1", dq.ACTION_APPROVE, queue_path=self.queue_path,
        )

        for _ in range(3):
            distribution_store.apply_action(
                "v1", dq.ACTION_PUBLISH, queue_path=self.queue_path,
            )
            entry = distribution_store.apply_action(
                "v1", dq.ACTION_MARK_FAILED, queue_path=self.queue_path,
            )

        final = distribution_store.apply_action(
            "v1", dq.ACTION_PUBLISH, queue_path=self.queue_path,
        )
        self.assertEqual(final["retry_count"], 3)


if __name__ == "__main__":
    unittest.main()
