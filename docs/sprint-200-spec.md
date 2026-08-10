# Sprint200 SPEC — Closed Beta RC 사용자 여정 확인

- 상태: 완료 (구현 · 실측 · 검증 통과)
- 선행: Sprint199 `cfb1f37`
- 기준선: regression `ran=4159 failures=0 errors=0`
- 결과: regression `ran=4181 failures=0 errors=0`

## 실측 (세 경우)

| 걸음 | 자료 없음 | 정상 | 깨짐 |
|---|---|---|---|
| 1. 새 자리 설치 | X | X | X |
| 2. 첫 실행 | ? 1벌 | ? 3벌 | ? 4벌 |
| 3. 자료 연결 | ? 0벌 | ? 2벌 | ? 3벌 |
| 4. 대본 준비 | X 0벌 | O 2벌 | O 2벌 |
| 5. 이미지·음성 자료 | ? | ? | ? |
| 6. 제작 시작 | ? 0벌 | ? 1벌 | ? 1벌 |
| 7. 렌더 완료 | X 0벌 | O 1벌 | O 1벌 |
| 8. 결과 확인 | ? | ? | ? |
| 오류 종류 | 없음 | 없음 | `ffmpeg_missing 1` |

Gate와 대조한 열한 항목이 세 경우 모두 일치했다 — Flow 다섯 칸,
Readiness 세 줄, 오류 종류, 확인 시점, 자료 걸음은 모름.

밖으로 나가도 되는가: 새어 나온 낱말 없음 · 절대 경로 없음 · 최종
판단 문구 없음 · Traceback 없음 · 두 번 더 불러도 데이터 폴더와 기록
그대로 · **기록을 읽은 횟수 1회**.

깨진 기록(`{ 이건 json이 아니다`)을 넣어도 죽지 않는다.

### 8번 걸음이 실측에서 늘 FIRST_RUN인 이유

실측은 프로젝트 없이(`project_path=None`) 돌았다. `onboarding_state`는
기록이 아니라 디스크의 현재 상태를 보므로, 실제 프로젝트를 열어야
`COMPLETED`/`REVIEW_REQUIRED`/`FAILED`가 나온다. API는 `project_id`를
받아 그 경로를 넘긴다(`/api/onboarding-state`와 같은 방식).

---

## 1. 목표

Sprint191~199가 만든 것은 **운영자가 보는 층**이었다. 이번은 방향이
다르다 — "처음 받아서 켠 사람이 끝까지 갈 수 있는가"를 본다.

다만 **가 봤다고 말할 수는 없다.** 우리가 할 수 있는 것은 여덟 걸음
각각에 대해 "지금 확인되는 것", "아직 세는 자리가 없는 것", "다음에
할 일"을 늘어놓는 것뿐이다.

그래서 이 표는 "통과"라고 말하지 않는다.

---

## 2. 착수 전에 짚어야 할 것 둘

### 2.1 `asset_ready`라는 사건은 없다

의뢰의 정상 흐름은 이렇게 적혀 있다.

```
workspace_selected → script_ready → asset_ready → render_completed
```

`beta_telemetry`가 아는 이름은 다르다.

```python
WORKSPACE_SELECTED = "workspace_selected"
SCRIPT_READY       = "script_ready"
PREPARATION_READY  = "preparation_ready"   # <- asset_ready 가 아니다
RENDER_STARTED     = "render_started"
RENDER_COMPLETED   = "render_completed"
```

없는 이름으로 테스트를 쓰면 그 테스트는 아무것도 지키지 못한다.
**실제 이름 `preparation_ready`를 쓴다.**

### 2.2 그 사건은 모아 세지 않는다

더 중요한 것이 있다. `beta_dashboard`가 세는 것은 다섯이다.

```
workspace_selected · script_ready · render_started
render_completed · render_failed
```

`preparation_ready`는 **기록에 남지만 모아 세는 자리가 없다.**
그래서 "이미지/음성 자료 확인" 걸음에는 댈 숫자가 없다.

세는 자리를 새로 만드는 것은 금지(새 데이터 수집)이므로, 이 걸음은
**`?`로 두고 왜 모르는지를 적는다.** `beta_readiness`가 테스트 결과
줄에서 이미 쓰는 방식이다 — X로 찍으면 "실패했다"로 읽히고 O로 찍으면
거짓이다.

---

## 3. 여덟 걸음과 그 근거

**모든 값은 이미 있는 자리가 낸 답이다.** 새 기준을 만들지 않는다.

| # | 걸음 | 무엇으로 말하는가 | 판정하는 자리 |
|---|---|---|---|
| 1 | 새 자리 설치 | `executable` · `data_separated` | `beta_readiness` |
| 2 | 첫 실행 | `start` 수 | `beta_funnel` |
| 3 | workspace 선택 | `workspace_selected` 수 | `beta_funnel` |
| 4 | 대본 준비 | `free_flow` · `script_ready` 수 | `beta_readiness` · `beta_funnel` |
| 5 | 이미지/음성 자료 | **`?` — 모아 세는 자리가 없음** | 없음 (2.2) |
| 6 | 제작 시작 | `render_started` 수 | `beta_funnel` |
| 7 | 렌더 완료 | `render_done` · `render_completed` 수 | `beta_readiness` · `beta_funnel` |
| 8 | 결과 확인 | `COMPLETED` / `REVIEW_REQUIRED` / `FAILED` | `onboarding_state` |

### 여기서 세지 않는다 — 특히 `> 0` 을 만들지 않는다

`count > 0`은 그 자체가 새 기준이다. `beta_readiness`는 이미
`script_ready > 0`을 판정해 `free_flow` 줄에 담아 두었다. 그 답을
가져오는 것과, 여기서 다시 `> 0`을 쓰는 것은 다르다 — 후자는 두
자리가 다른 기준을 갖게 되는 첫걸음이다.

그래서 각 걸음은 **숫자를 그대로 싣고**, `ok`는 **이미 판정된 줄이
있을 때만** 그 값을 옮긴다. 없으면 `None`이다.

---

## 4. 다음 행동을 알 수 있는가

의뢰의 확인 항목 중 하나다. 이것은 표에 담을 값이 아니라 **성질**이라
테스트로 본다.

`onboarding_state.SAYS`는 열 가지 상태마다 (제목, 할 말, 다음에 할 일,
이어서 갈 수 있는가)를 갖고 있다. 그러니 확인할 것은 하나다.

> **어느 상태에 있든 `next_action`이 비어 있지 않은가**

열 상태를 전부 훑어 확인한다. 새 문구를 만들지 않고, 이미 있는 표가
빠짐없이 채워져 있는지만 본다.

---

## 5. 말하지 않는 것

금지: `통과` · `배포 가능` · `문제 없음` · `안전함` · `출시 준비 완료`

허용: `확인됨` · `현재 단계` · `다음 행동` · `아직 모릅니다`

Sprint199에서 겪은 함정을 그대로 피한다 — 금지 문구는 **긍정형만**
둔다. `beta_readiness.CAUTION`에 "내보내도 된다는 뜻은 아닙니다"가
글자로 들어 있어, 부분 문자열로 찾으면 부정문에 걸려 거짓 판정이 난다.

탐침 낱말도 마찬가지다. 개인정보 검사에 "사람" 같은 흔한 말을 쓰면
우리 글에 걸린다. `홍길동`을 쓴다(Sprint199에서 겪음).

---

## 6. 무엇을 읽는가

```
beta_release_gate.build()      <- 숫자·readiness·flow·주의사항 전부
onboarding_state.build(...)    <- 지금 어디에 있는가 · 다음 행동
troubleshooting.build(...)     <- 막혔을 때 어떻게 하는가
```

`beta_summary`·`beta_readiness`를 **따로 부르지 않는다.** Gate가 이미
기록을 한 번만 읽고 그 결과를 들고 있다. 다시 부르면 그것이 두 번째
읽기가 되고, Sprint190·192·193·199가 네 번 지킨 원칙이 무너진다.

`onboarding_state`와 `troubleshooting`은 기록이 아니라 **디스크의
현재 상태**를 본다. 사는 자리가 달라 겹치지 않는다.

---

## 7. 화면

- 헤더 버튼 `처음 사용자 테스트`
- 카드에 여덟 걸음, 현재 단계와 다음 행동, 주의사항
- 복사는 서버가 지은 글을 그대로 쓴다(Sprint174 규칙)

라우터 `GET /api/beta-release-candidate`, contract 등록.

---

## 8. 검증 계획

신규 `tests/test_beta_release_candidate.py`.

### A. 신규 사용자

1. 상태가 `FIRST_RUN`이다
2. `next_action`이 비어 있지 않다
3. 절대 경로가 없다 · 사용자명이 없다

### B. 정상 흐름

`workspace_selected` → `script_ready` → `preparation_ready` →
`render_started` → `render_completed` 기록을 놓고

4. 각 걸음의 수가 `beta_release_gate`의 flow와 같다
5. readiness O/X/? 가 Gate와 같다
6. 5번 걸음(자료)이 `?`이고 detail이 이유를 말한다
7. 상태가 `onboarding_state.build()`가 낸 것과 같다

### C. 실패 흐름

없는 폴더 · 깨진 기록 · 렌더 실패

8. 오류 종류가 Gate가 낸 것과 같다
9. traceback 경로가 없다 · 사용자 경로가 없다
10. 예외로 죽지 않는다

### D. 재실행

11. 두 번 불러도 데이터 폴더가 그대로다
12. 새 사건이 생기지 않는다
13. 기록을 **한 번만** 읽는다

### E. 말하지 않는 것

14. 금지 문구 다섯이 없다
15. `caution`이 그대로 실려 있다
16. 소스에 `sum(`/`len(`/`max(`/`min(`/`sorted(`가 없다 (AST)
17. 소스가 `beta_summary`·`beta_readiness`·`beta_dashboard`를 직접
    부르지 않는다 (6절)

### F. 다음 행동

18. `onboarding_state.SAYS`의 열 상태 모두 `next_action`이 있다

### G. 서버와 화면

19. API가 답한다 · 서비스와 숫자가 같다
20. 화면에 `처음 사용자 테스트`가 있다

### H. 실측

zip → 새 폴더 → PATH System32만. 세 경우(자료 없음 / 정상 / 깨짐).

### I. regression

`fail=0 error=0`, 기준선 4159 + 신규분, 우회 없이.

---

## 9. 완료 조건

- [ ] `app/services/beta_release_candidate.py` 신규
- [ ] `GET /api/beta-release-candidate` · contract 등록
- [ ] `처음 사용자 테스트` 버튼과 복사
- [ ] 여덟 걸음 · 5번은 `?`와 이유
- [ ] 숫자가 Gate와 일치 · 기록 읽기 1회
- [ ] 금지 문구 없음 · caution 유지
- [ ] 개인정보 없음 · 파일 쓰기 없음 · 새 사건 없음
- [ ] 실측 세 경우
- [ ] regression `fail=0 error=0`
- [ ] 로컬 커밋까지. **Push 안 함**

---

## 10. 하지 않는 것

- **`preparation_ready`를 세는 자리를 만드는 것.** 새 데이터 수집이다.
  5번 걸음은 `?`로 둔다
- **`asset_ready`라는 이름을 쓰는 것.** 없는 이름이다
- **실제로 렌더를 돌려 보는 것.** 이 표는 기록을 읽을 뿐이다
- Render Engine · Provider · Pipeline · Free Mode · Upload
