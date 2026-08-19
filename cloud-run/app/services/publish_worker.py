"""
Sprint237 - 줄에 선 것을 집어 올린다 (Publish Automation, Phase 5).

Sprint235 가 줄을 만들었고 아무도 집지 않았다. 화면은 "줄에 세웠습니다.
올리는 것은 아직입니다" 라고 정직하게 적고 있었다. 이제 집는 쪽이다.

일꾼이 하는 일은 셋뿐이다
-------------------------
    집는다   publish_queue.claim - 집는 것이 곧 잠그는 것이다
    부른다   그 플랫폼의 upload_step_service
    적는다   SUCCESS(주소) 또는 FAILED(이유 · 다시 해 볼 만한가)

올리는 법을 여기서 알지 않는다
------------------------------
세 플랫폼의 스텝 서비스가 이미 안다 - 플래그 확인, 자격증명 확인,
로그인 확인, Adapter 조립, 결과 파일 남기기까지. 그것을 여기에 다시
쓰면 같은 일을 두 곳이 하게 되고 어느 날 한쪽만 고쳐진다.

그래서 이 파일은 Adapter 도 Runtime 도 모른다. Sprint235 가 세운
경계가 그것이다 - Adapter 를 쓰는 곳은 스텝 서비스뿐이고 Queue ·
Workflow · UI 는 모른다. 일꾼도 그 바깥이다.

한 번에 하나씩
--------------
run_once 는 하나만 집는다. 여러 개를 한 번에 집으면 중간에 프로그램이
꺼졌을 때 어디까지 갔는지 알 수 없다. 줄을 비우고 싶으면 drain 이
run_once 를 반복한다 - 그 사이에 사람이 껐다 켜도 남은 것은 줄에
그대로 있다.

무엇을 실패로 적는가
--------------------
스텝이 success=False 를 돌려주면 그것이 실패다. 스텝이 예외로 터져도
실패다 - 그때는 다시 해 볼 만한 것으로 적는다. 무슨 일인지 모르는데
"다시 해도 소용없다" 고 단정하면 사람은 다시 시도할 길을 잃는다.
"""


def _steps() -> dict:
    """
    플랫폼마다 누가 올리는가. 부를 때 들인다 - 이 모듈을 import 하는
    것만으로 세 플랫폼의 무거운 짐이 따라오면 안 된다.
    """

    from app.services import (
        instagram_upload_step_service, tiktok_upload_step_service,
        youtube_upload_step_service,
    )

    return {
        "youtube": youtube_upload_step_service.run_youtube_upload_step,
        "instagram": instagram_upload_step_service.run_instagram_upload_step,
        "tiktok": tiktok_upload_step_service.run_tiktok_upload_step,
    }


class _Steps:
    """
    STEPS 를 보는 것만으로 세 모듈을 들이지 않는다. 이름은 미리 알고,
    함수는 물을 때 찾는다.
    """

    NAMES = ("youtube", "instagram", "tiktok")

    def __iter__(self):
        return iter(sorted(self.NAMES))

    def __len__(self):
        return len(self.NAMES)

    def __contains__(self, name):
        return name in self.NAMES

    def __getitem__(self, name):
        return _steps()[name]

    def get(self, name, default=None):
        return _steps().get(name, default)


STEPS = _Steps()


def _store(store_path: str = None) -> str:
    from app.services import publish_queue

    return store_path or publish_queue.default_store_path()


def recover(store_path: str = None) -> list:
    """
    켤 때 한 번 부른다. 올리던 중에 끊긴 것을 다시 세운다 - 그대로
    두면 아무도 집지 않는데 사람은 올라가는 중인 줄 안다.
    """

    from app.services import publish_queue

    return publish_queue.recover_stuck(_store(store_path))


def run_once(store_path: str = None, topic: str = "", steps=None):
    """
    하나를 집어 올린다. 집을 것이 없으면 None.

    steps 는 시험이 갈아 끼우는 자리다 - 실제 업로드를 부르지 않고
    이 흐름만 재기 위해서다.
    """

    from app.services import project_service, publish_queue

    where = _store(store_path)

    row = publish_queue.claim(where)

    if row is None:
        return None

    steps = STEPS if steps is None else steps
    platform = row["platform"]

    step = steps.get(platform) if hasattr(steps, "get") else None

    if step is None:
        # 다시 세워도 그 플랫폼은 생기지 않는다.
        return publish_queue.mark_failed(
            where, row["id"],
            reason=f"올릴 줄 모르는 곳입니다: {platform}", retryable=False)

    try:
        project_path = project_service.resolve_project_path(row["project_id"])
    except Exception as failed:
        # 없는 프로젝트는 다시 시도해도 생기지 않는다.
        return publish_queue.mark_failed(
            where, row["id"], reason=str(failed), retryable=False)

    # Sprint238 - 집은 뒤에 한 번 더 본다.
    #
    # 줄에 세운 다음 누가 손으로 올렸을 수도 있고, 그 사이는 얼마든지
    # 길 수 있다. 한 겹만 두면 그 겹을 지나온 길이 하나라도 생기는 날
    # 뚫린다.
    from app.services import publish_history

    done = publish_history.already_published(project_path, platform)

    if done:
        return publish_queue.mark_success(
            where, row["id"], url=done.get("url") or "")

    try:
        found = step(topic or row["project_id"], project_path, {}) or {}
    except Exception as failed:
        # 무슨 일인지 모른다. 모르면 다시 해 볼 수 있게 남긴다.
        return publish_queue.mark_failed(
            where, row["id"],
            reason=f"{type(failed).__name__}: {failed}", retryable=True)

    if found.get("success"):
        return publish_queue.mark_success(
            where, row["id"], url=found.get("url") or "")

    return publish_queue.mark_failed(
        where, row["id"],
        reason=str(found.get("error") or "이유를 알 수 없습니다."),
        retryable=bool(found.get("retryable")))


def drain(store_path: str = None, topic: str = "", steps=None,
          limit: int = 50) -> list:
    """
    줄이 빌 때까지 하나씩 집는다.

    limit 이 있는 이유는 실패가 곧바로 다시 PENDING 이 되는 날을
    대비해서다 - 그런 날에도 이 함수는 끝나야 한다.
    """

    done = []

    for _ in range(max(0, int(limit))):
        found = run_once(store_path, topic=topic, steps=steps)

        if found is None:
            break

        done.append(found)

    return done
