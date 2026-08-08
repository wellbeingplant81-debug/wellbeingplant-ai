"""
Sprint168 - 설명 없이도 끝까지 갈 수 있게 (Epic 57, Phase 19).

Sprint150~167이 기능을 다 만들었다. 그런데 처음 쓰는 사람은 화면을
열고 "그래서 지금 뭘 눌러야 하지"를 묻는다. 자료를 넣어야 하는지,
대본을 붙여야 하는지, 만들어도 되는지가 여러 판에 흩어져 있었다.

한 자리에서 지금 상태와 다음 할 일을 말한다
-------------------------------------------
새 사실을 만들지 않는다. 이미 있는 네 곳에서 읽는다.

    workspace      폴더와 개수
    preparation    Scene별 준비 상태
    final-check    지금 만들 수 있는가
    output-check   만든 결과가 쓸 만한가

다음 할 일은 그 넷에서 나온다 - 어디에 막혀 있는가가 곧 무엇을
해야 하는가다.

말은 사실만
-----------
    허용   준비됨 · 검토 필요 · 부족 · 검사 통과 · 수정 필요
    금지   최고 · 추천 · 품질 점수 · AI 평가 · 가성비 · 저렴

"무료 제작 모드"는 모드의 이름이라 그대로 둔다 - 그 모드가 실제로
API를 부르지 않는다는 사실을 가리키는 말이고, 값어치에 대한 판단이
아니다. 금지되는 것은 상태를 말하는 자리에서 값을 주장하는 것이다.

무엇을 지키는가
---------------
    1. 다음 할 일을 말한다     test_free_mode_home_guides_next_action
    2. 요약이 실제를 읽는다     test_free_mode_summary_reads_real_state
    3. 기존 길만 부른다        test_free_mode_buttons_keep_existing_routes
    4. 새로 열어도 그대로다     test_free_mode_reload_keeps_state
    5. 값을 주장하지 않는다     test_free_mode_has_no_marketing_claims
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi.testclient import TestClient

from app.main import app
from app.routers import studio as studio_router
from app.services import audio_policy, free_workspace, output_check

PAGE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "app", "static", "studio.html",
)

# 상태를 말하는 자리에서 쓰면 안 되는 말들. 값어치에 대한 주장이다.
BANNED = ("최고", "추천", "품질 점수", "AI 평가", "가성비", "저렴",
          "훌륭", "우수")


def _page():
    with open(PAGE, encoding="utf-8") as f:
        return f.read()


def _script(strip_comments=True):
    page = _page()
    source = page[page.index("<script>"):page.rindex("</script>")]

    if strip_comments:
        # 줄 전체가 주석인 것은 걷어낸다 - 코드를 보는 검사인데
        # 설명을 읽으면 제 주석에 걸린다(이 저장소가 여러 번 겪었다).
        source = re.sub(r"(?m)^[ \t]*//.*$", "", source)

    return source


def _block(name):
    """그 함수의 본문만."""

    source = _script()
    start = source.index(f"function {name}(")

    return source[start:source.index("\n}", start)]


def _png(path, color=(200, 30, 30)):
    from PIL import Image

    os.makedirs(os.path.dirname(path), exist_ok=True)
    Image.new("RGB", (1080, 1920), color).save(path)


def _wav(path, seconds=1.5):
    os.makedirs(os.path.dirname(path), exist_ok=True)

    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", f"sine=f=440:d={seconds}"]
        + audio_policy.pcm_output_args() + [path],
        capture_output=True, check=True,
    )


def _mp4(path, seconds=4.5):
    os.makedirs(os.path.dirname(path), exist_ok=True)

    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi",
         "-i", f"color=c=cyan:s=1080x1920:d={seconds}",
         "-f", "lavfi", "-i", f"sine=f=440:d={seconds}",
         "-pix_fmt", "yuv420p", "-shortest", path],
        capture_output=True, check=True,
    )


class NextActionTest(unittest.TestCase):
    """1. 다음 할 일을 말한다."""

    def test_free_mode_home_guides_next_action(self):
        source = _script()

        self.assertIn("function freeHome", source)
        self.assertIn("function freeNextStep", source)

        body = _block("freeNextStep")

        # 사양이 정한 네 단추가 다 있다.
        for label in ("자료 확인", "제작 준비", "영상 만들기", "결과 보기"):
            with self.subTest(label=label):
                self.assertIn(label, body)

    def test_the_next_step_is_derived_not_stored(self):
        """
        다음 할 일을 어딘가에 적어 두지 않는다.

        적어 두면 실제 상태와 갈리고, 화면이 "만들 수 있다"고 한 것을
        서버가 거절하는 날이 온다.
        """

        body = _block("freeNextStep")

        for name in ("workspace", "preparation", "finalCheck", "outputCheck"):
            with self.subTest(name=name):
                self.assertIn(name, body)

    def test_the_home_shows_the_three_blocks(self):
        body = _block("freeHome")

        for label in ("자료 준비", "대본 준비", "제작 준비"):
            with self.subTest(label=label):
                self.assertIn(label, body)


class SummaryReadsRealStateTest(unittest.TestCase):
    """2. 요약이 실제를 읽는다."""

    def setUp(self):
        self.workspace = tempfile.mkdtemp()
        self.project = tempfile.mkdtemp()
        self.store = os.path.join(tempfile.mkdtemp(), "free_workspace.json")

        for path in (self.workspace, self.project,
                     os.path.dirname(self.store)):
            self.addCleanup(shutil.rmtree, path, ignore_errors=True)

        self.client = TestClient(app)

        self._real_project = studio_router._project_path
        self._real_store = studio_router._workspace_store

        studio_router._project_path = lambda project_id: self.project
        studio_router._workspace_store = lambda: self.store

        self.addCleanup(self._restore)

        # Scene마다 다른 낱말을 쓴다 - 같은 낱말을 나누면 한 자료가
        # 여러 Scene에 걸려 "검토 필요"가 된다(Sprint156). 실제 대본은
        # Scene마다 다른 것을 말한다.
        self.actions = ["무릎 스트레칭", "허리 세우기"]

        self.scenes = [
            {"scene": n, "narration": f"{n}번 문장입니다.",
             "image_prompt": self.actions[n - 1]}
            for n in (1, 2)
        ]

        with open(os.path.join(self.project, "script.json"), "w",
                  encoding="utf-8") as f:
            json.dump({"title": "t", "scenes": self.scenes}, f,
                      ensure_ascii=False)

        with open(os.path.join(self.project, "project.json"), "w",
                  encoding="utf-8") as f:
            json.dump({"topic": "t", "channel": "wellbeing",
                       "production_source": "import",
                       "image_provider": "local_stock",
                       "voice_provider": "local_voice"}, f,
                      ensure_ascii=False)

    def _restore(self):
        studio_router._project_path = self._real_project
        studio_router._workspace_store = self._real_store

    def whole(self):
        for n in (1, 2):
            _png(os.path.join(self.workspace, "images",
                              f"{self.actions[n - 1]}.png"))
            _wav(os.path.join(self.workspace, "voices", f"scene{n}.wav"))
            _png(os.path.join(self.project, "images", f"scene{n}.png"))
            _wav(os.path.join(self.project, "audio", "scenes",
                              audio_policy.scene_audio_filename(n)))

        srt = os.path.join(self.project, "subtitle", "subtitle.srt")
        os.makedirs(os.path.dirname(srt), exist_ok=True)

        with open(srt, "w", encoding="utf-8") as f:
            f.write("1\n00:00:00,000 --> 00:00:01,500\n문장\n")

        _mp4(os.path.join(self.project, "video", "final_short.mp4"))

        self.client.put("/studio/api/workspace",
                        json={"root": self.workspace})
        self.client.post("/studio/api/review/p1/library", json={})

    def test_free_mode_summary_reads_real_state(self):
        """
        요약의 다섯 칸이 전부 서버가 낸 값이다.

        화면이 스스로 재거나 세면 실제와 갈린다.
        """

        self.whole()

        report = self.client.get(
            "/studio/api/review/p1/completion").json()

        self.assertEqual(report["script"]["source"], "import")
        self.assertEqual(report["image"]["provider"], "local_stock")
        self.assertEqual(report["voice"]["provider"], "local_voice")
        self.assertAlmostEqual(report["video"]["seconds"], 4.5, delta=0.3)
        self.assertEqual(report["output"]["state"], output_check.READY)

        # 사람이 고른 것이 있으면 그 사실도 온다.
        picked = os.path.join(self.workspace, "images",
                              f"{self.actions[1]}.png")

        self.client.put("/studio/api/review/p1/scenes/1/asset",
                        json={"path": picked})

        rows = {r["scene"]: r for r in
                self.client.get("/studio/api/review/p1/completion")
                .json()["scene_rows"]}

        self.assertEqual(rows[1]["image_source"], "override")

    def test_the_screen_draws_those_fields(self):
        body = _block("freeSummary")

        for field in ("script", "image", "voice", "video", "output"):
            with self.subTest(field=field):
                self.assertIn(field, body)

    def test_the_home_counts_come_from_the_server(self):
        self.whole()

        workspace = self.client.get("/studio/api/workspace").json()
        prepared = self.client.get(
            "/studio/api/review/p1/preparation").json()

        self.assertEqual(workspace["counts"]["images"], 2)
        self.assertEqual(workspace["counts"]["voice"], 2)
        self.assertEqual(prepared["total"], 2)
        self.assertEqual(prepared["state"], free_workspace.READY)


class ExistingRoutesTest(unittest.TestCase):
    """3. 기존 길만 부른다."""

    def test_free_mode_buttons_keep_existing_routes(self):
        """
        화면이 부르는 모든 자리가 서버에 실제로 있다.

        없는 자리를 부르면 사람은 누르고 404를 본다 - 오타 하나로도
        그렇게 된다.
        """

        registered = [
            path.split("/") for path in app.openapi()["paths"]
        ]

        called = set(re.findall(r'"(/studio/api/[^"`]*)"', _script()))
        called |= set(re.findall(r"`(/studio/api/[^`]*)`", _script()))

        self.assertTrue(called)

        for path in sorted(called):
            bare = path.split("?")[0]

            # 값이 통째로 뒤에 붙는 자리는 정적으로 알 수 없다
            # (reviewCall의 `${project}${suffix}`가 그렇다). 그런
            # 것은 여기서 보지 않는다 - 억지로 맞히면 검사가 거짓이
            # 된다.
            if re.search(r"\}\$\{", bare) or bare.endswith("}"):
                continue

            parts = bare.split("/")

            with self.subTest(path=path):
                matched = any(
                    len(known) == len(parts)
                    and all(
                        # 등록된 {param} 자리는 아무 값이나 받는다.
                        k.startswith("{") or k == p
                        for k, p in zip(known, parts)
                    )
                    for known in registered
                )

                self.assertTrue(
                    matched, f"서버에 없는 자리를 부른다: {path}")

    def test_no_new_generation_route_was_added(self):
        """
        만드는 자리를 새로 만들지 않았다.

        이 Sprint는 흐름만 정리한다.
        """

        registered = {
            path for path in app.openapi()["paths"]
            if path.startswith("/studio/api")
        }

        # Sprint167까지 있던 것들. 늘었다면 이 Sprint가 만든 것이다.
        self.assertNotIn("/studio/api/review/{project_id}/free-render",
                         registered)
        self.assertNotIn("/studio/api/free/generate", registered)

    def test_the_home_button_uses_the_render_path_everyone_uses(self):
        body = _block("freeNextStep")

        # 만들기는 기존 승인 흐름을 그대로 탄다.
        self.assertIn("reviewApprove", body)


class ReloadKeepsStateTest(SummaryReadsRealStateTest):
    """4. 새로 열어도 그대로다."""

    def test_free_mode_reload_keeps_state(self):
        self.whole()

        picked = os.path.join(self.workspace, "images",
                              f"{self.actions[1]}.png")
        self.client.put("/studio/api/review/p1/scenes/1/asset",
                        json={"path": picked})

        # 브라우저를 새로 연다.
        fresh = TestClient(app)

        self.assertEqual(
            fresh.get("/studio/api/workspace").json()["root"], self.workspace)

        report = fresh.get("/studio/api/review/p1/completion").json()

        self.assertEqual(report["image"]["provider"], "local_stock")
        self.assertEqual(report["output"]["state"], output_check.READY)

        rows = {r["scene"]: r for r in report["scene_rows"]}

        self.assertEqual(rows[1]["image_source"], "override")

    def test_the_screen_reloads_instead_of_remembering(self):
        """
        화면이 상태를 들고 있지 않는다.

        새로 열 때마다 서버에서 읽는다 - 들고 있으면 다른 창에서
        고친 것이 안 보인다.
        """

        body = _block("openReview")

        self.assertIn("loadPreparation", body)


class NoMarketingClaimsTest(unittest.TestCase):
    """5. 값을 주장하지 않는다."""

    def test_free_mode_has_no_marketing_claims(self):
        """
        상태를 말하는 자리에서 값어치를 주장하지 않는다.

        "무료 제작 모드"는 모드의 이름이라 그대로 둔다 - 그 모드가
        실제로 API를 부르지 않는다는 사실이고, 값에 대한 판단이 아니다.
        """

        for name in ("freeHome", "freeNextStep", "freeSummary"):
            body = _block(name)

            for word in BANNED:
                with self.subTest(name=name, word=word):
                    self.assertNotIn(word, body)

    def test_the_status_labels_are_the_allowed_ones(self):
        source = _script()

        declared = source[source.index("const STATE_LABEL"):]
        declared = declared[:declared.index("};") + 2]

        for word in BANNED:
            with self.subTest(word=word):
                self.assertNotIn(word, declared)

    def test_no_price_is_claimed_anywhere_on_the_screen(self):
        """
        값을 안다고 말하지 않는다.

        아는 것은 "API를 부르는가"뿐이다 - Sprint151이 정한 그 말을
        쓴다.
        """

        source = _script()

        self.assertNotIn('"무료"', source)
        self.assertIn("API 비용 없음", source)

    def test_the_words_we_do_use_are_facts(self):
        source = _script()

        for word in ("준비 완료", "검토 필요", "부족"):
            with self.subTest(word=word):
                self.assertIn(word, source)


if __name__ == "__main__":
    unittest.main()
