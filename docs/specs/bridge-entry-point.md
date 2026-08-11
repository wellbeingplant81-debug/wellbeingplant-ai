# AI Bridge 진입점 감싸개 (SPEC)

OS Activation Batch 2. AI Bridge 쪽 사슬(Phase 38~52)이 이 제품을 부를 수 있게
**감싸개 하나**를 둔다. 제품 기능·UI·설계는 한 글자도 바뀌지 않는다.

---

## 1. 왜 이 저장소인가

Bridge 쪽 규칙(Phase 47)은 두 조건뿐이다: 순환 의존이 생기는가 / Bridge 에서
import 가능한가.

실측:

```
pyproject.toml · setup.py       없음  → 설치 가능한 패키지 선언이 없다
파이썬 파일                     513개
진입면                          FastAPI 라우트 89개(라우터 14) + run_pipeline() 하나
ai_bridge 를 import 하는 파일    0
```

순환은 없다. 그러나 **Bridge 에서 이 코드를 import 할 수단이 없다.** 그래서
감싸개는 여기다. 그리고 이 감싸개도 `ai_bridge` 를 import 하지 않는다 --
계약이 `Protocol` 이라 `execute(request)` 하나면 구조적으로 만족한다.

## 2. ⚠⚠ 이 제품의 진입점은 **영상 한 편을 만드는 일 전체**다

`run_pipeline(topic, project_path, channel, …)` 는 이름 그대로다. 부르면
대본(LLM) · 스톡 검색 · 이미지 · TTS · 자막 · 합성 · 썸네일이 **실제로 돈다.**

그리고 **마지막이 업로드다**:

```python
# Sprint92 - 업로드. 반드시 마지막이다.
upload = studio_upload.run_upload_quietly(project_path, …)
```

그 파일이 스스로 적는다 -- *"갓 만든 프로젝트는 아직 사람이 보지 않았으므로
승인 상태가 아니고, studio_upload 가 그것을 보고 건너뛴다."* 제품 자신의 관문이
있다는 뜻이지 **업로드 경로가 없다는 뜻이 아니다.** 이미 승인된 프로젝트
경로를 주면 올라간다.

> 그래서 다른 어떤 제품보다 **플래그가 중요하다.** *"부를 수 있다"* 와
> *"불러도 된다"* 는 여기서 완전히 다른 물음이다.

## 3. 플래그 — 배송 기본값 `False`

```python
ENABLE_REAL_VIDEO_PIPELINE = False
```

꺼져 있으면 파이프라인을 **부르지 않는다**(`NEVER_RAN`). **켜는 코드는 이
저장소에 없다.**

## 4. 파이프라인을 import 하지 않고 **주입받는다**

`from app.pipeline import pipeline` 을 모듈 최상단에 두면 import 만으로
`requirements.txt` 77줄이 전부 필요해진다(`google.genai` · `moviepy` …).
감싸개가 그것을 끌고 오면 *"감싸개를 얹었더니 import 가 무거워졌다"* 가 된다.

그래서 **부를 것을 받는다.** 없으면 `BLOCKED` 다.

## 5. 요청은 세 값을 **선언**받는다

```python
@dataclass(frozen=True, kw_only=True)
class VideoRequest:
    topic: str
    project_path: str
    channel: str
```

셋 중 하나라도 비면 `BLOCKED` 다. **기본값을 지어내지 않는다** -- `project_path`
를 추측하면 남의 프로젝트 폴더에 영상을 쓰게 되고, `channel` 을 추측하면 엉뚱한
채널로 올라간다.

## 6. ⚠ 회귀에 대해 정직하게

**이 환경에서는 기존 스위트 228 파일이 원래 돌지 않는다.** 감싸개 때문이 아니라
**이 감싸개 이전부터** 그렇다:

```
.venv                없음
dotenv               MISSING   ← app/__init__.py 가 최상단에서 부른다
moviepy · google.genai  MISSING
```

`app/__init__.py` 가 `load_dotenv()` 를 부르므로 `app` 을 import 하는 모든
테스트가 수집 단계에서 멈춘다. 이것을 고치는 것은 이 저장소의 환경 구성 문제이고
**감싸개 하나를 얹는 일의 범위가 아니다** -- 77줄짜리 의존성을 설치하는 것은
"Bridge 연결에 필요한 최소 변경" 이 아니다.

그래서 **감싸개 테스트는 `app/__init__.py` 를 거치지 않고 파일 경로로 모듈을
직접 불러온다.** 우회가 아니라 증명이다: 감싸개는 제품 의존성을 하나도 쓰지
않으므로 아무것도 설치되지 않은 인터프리터에서 불려야 하고, 실제로 불린다.

| | |
|---|---|
| 감싸개 테스트 13개(+서브테스트 3) | **통과** |
| 기존 스위트 228 파일 | **돌릴 수 없음**(의존성 미설치, 기존 상태) |

## 7. 범위

| | |
|---|---|
| 새 파일 | `cloud-run/app/bridge/entry_point.py` · 테스트 1 · 이 SPEC |
| 기존 파일 변경 | **0** |
| 제품 기능·UI·리팩터링 | **0** |
| `ai_bridge` import | **0** |
| 실제 렌더링·업로드·API 호출 | **0** (플래그 `False`) |
| Git Push | **하지 않는다** |

---

**SPEC → RED → GREEN → REGRESSION → 로컬 COMMIT**
