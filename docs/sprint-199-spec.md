# Sprint199 SPEC — Beta Release Gate

- 상태: 완료 (구현 · 실측 · 검증 통과)
- 선행: Sprint191~198, 마지막 `58ee822`
- 기준선: regression `ran=4136 failures=0 errors=0`
- 결과: regression `ran=4159 failures=0 errors=0`

---

## 1. 목표

Sprint191~198이 만든 베타 운영 자리들을 **한 장에서** 본다. 여기서
새로 세거나 판정하지 않는다. 이미 있는 답을 모아 놓을 뿐이다.

이름이 Gate지만 **문을 여닫지 않는다.** 이 표는 "지금 확인된 것"과
"아직 모르는 것"을 늘어놓고, 문을 열지 말지는 사람이 정한다.

---

## 2. 이미 있는 사슬

Sprint190·192·193이 같은 원칙을 세 번 세웠다 — **기록은 한 번만 읽고
그 하나를 나눠 준다.** 따로 읽으면 한 장 안에서 숫자가 어긋난다.

```
beta_dashboard.build()          <- 기록을 읽는 유일한 자리
        |
beta_summary.build()            한 번 읽고 다섯에게 나눔
        |
        +-- beta_readiness.build(summary)      <- Sprint192에 주입구가 생김
        |
beta_snapshot.build()           summary와 readiness를 묶고 시각을 찍음
        |
beta_release_report.build(snapshot)            <- Sprint193에 주입구가 생김
```

**주입구가 없는 자리가 하나 있다** — `beta_snapshot.build()`는 인자를
받지 않고 제 안에서 `beta_summary.build()`를 다시 부른다.

---

## 3. 한 번만 읽으려면 한 곳을 열어야 한다

Gate가 담아야 하는 것 중 `top_blocked_stage`·`error_kinds`·
`next_action`은 **summary에만** 있다. snapshot은 그것을 들고 다니지
않는다.

그래서 Gate는 summary와 snapshot을 둘 다 필요로 한다. 지금 구조로는
이렇게 된다.

```python
summary  = beta_summary.build()      # 기록 1차 읽기
snapshot = beta_snapshot.build()     # 그 안에서 또 읽는다  <- 2차
```

**기록을 두 번 읽는다.** 그 사이에 다른 작업이 기록을 늘리면 Gate 한
장 안에서 설치본 수와 흐름 숫자가 어긋난다. 세 스프린트가 없앤 바로
그 결함을 마지막 한 장에서 되살리는 셈이다.

### 제안 — Sprint192가 한 것을 그대로 한 번 더

```python
-def build() -> dict:
+def build(summary: dict = None) -> dict:
     ...
-    summary = beta_summary.build()
+    if summary is None:
+        summary = beta_summary.build()
```

`beta_readiness`가 Sprint192에 받은 것과 **같은 모양의 주입구**다.

- 판정 로직을 건드리지 않는다. 세는 곳도 고르는 곳도 그대로다
- 인자를 주지 않으면 예전과 완전히 같다 — 기존 호출부
  (`/api/beta-snapshot` 라우터, 테스트)는 손댈 필요가 없다
- 이것 하나로 Gate 전체가 **기록 1회 읽기**가 된다

이것이 이 스프린트에서 기존 파일을 고치는 **유일한 곳**이다.

### 하지 않는 대안

| | 왜 안 하는가 |
|---|---|
| 두 번 읽는 것을 받아들인다 | 숫자가 어긋날 수 있다. 세 스프린트가 없앤 결함이다 |
| Gate가 snapshot을 직접 조립한다 | 시각·flow·readiness를 다시 만드는 것이고, 그것이 곧 "새 계산"이다 |
| summary 없이 snapshot만 쓴다 | 멈춘 단계·오류 종류를 담을 수 없다. 요구 항목이 빠진다 |

---

## 4. 무엇을 담는가

전부 이미 있는 값이다. 오른쪽이 출처이고, Gate는 옮기기만 한다.

| # | 항목 | 담을 것 | 출처 |
|---|---|---|---|
| 1 | Beta Summary | 설치본 수 | `summary["installations"]` |
| | | 시작 → 완료 | `summary["started"]` · `["finished"]` · `["success_rate"]` |
| | | 가장 많이 멈춘 단계 | `summary["top_blocked_stage"]` |
| | | 오류 종류 | `summary["error_kinds"]` |
| 2 | Beta Readiness | O/X/? 와 설명 | `snapshot["readiness"]["checks"]` |
| | | 셈 | `["passed"]` · `["failed"]` · `["unknown"]` |
| 3 | Beta Snapshot | 확인 시점 | `snapshot["taken_at"]` |
| | | 기준 · 저장 안 함 | `snapshot["note"]` |
| 4 | Release Report | 버전 · 확인 시간 | `report["version"]` · `["checked_at"]` |
| | | Flow | `report["funnel"]` |
| | | 주의사항 | `report["cautions"]` |
| | | 붙여 넣을 글 | `report["report"]` |
| 5 | Diagnostic | 진단 정보 되는가 | `readiness` 의 `diagnostic` 줄 |

**5번을 위해 `diagnostic_report`를 따로 부르지 않는다.** `beta_readiness`
가 이미 그것을 물어보고 `diagnostic` 줄에 답을 담아 두었다. 다시 부르면
그것이 두 번째 읽기가 되고, 두 답이 어긋날 수 있다.

---

## 5. 새로 판정하지 않는다 — 어떻게 강제하는가

말로만 정하면 다음 사람이 무심코 깬다. 셋으로 묶는다.

1. **숫자가 같은지 본다.** Gate의 모든 수를 `summary`·`snapshot`·
   `report`가 낸 값과 하나씩 맞춰 본다. 하나라도 다르면 어딘가에서
   센 것이다
2. **금지 문구가 없는지 본다.** "배포 가능" · "출시 준비 완료" ·
   "안전함" · "배포해도 됩니다"
3. **소스에 세는 코드가 없는지 본다.** `beta_release_gate.py`에
   `sum(` · `len(` 같은 셈이 없는지 AST로 확인한다

### 함정 — 부정문에 걸리지 않게

`beta_readiness.CAUTION`은 이렇게 말한다.

> 전부 O여도 **내보내도 된다는 뜻은 아닙니다.**

여기에 "내보내도 된다"가 글자로 들어 있다. 금지 문구를 부분 문자열로
찾으면 **이 문장 때문에 거짓 판정이 난다.** 그래서 금지 목록은 위의
네 개처럼 긍정형만 두고, caution이 **그대로 실려 있는지**도 함께
확인한다.

---

## 6. 남기지 않고 새지 않는다

- **적지 않는다.** Gate는 읽기만 한다. 두 번 불러도 데이터 폴더가
  달라지지 않는지 본다
- **기록을 만들지 않는다.** `beta_telemetry` 사건이 늘지 않는지 본다
- **개인의 것이 없다.** 절대 경로·사용자명·피드백 글의 낱말이 없는지
  본다. Sprint192·193이 쓴 그 검사를 그대로 쓴다

---

## 7. 화면

- 헤더에 `배포 확인 정보` 버튼
- 누르면 카드가 뜨고, 글은 **서버가 짓는다**. 화면이 제 나름대로
  조립하면 받아 보는 글의 모양이 사람마다 달라진다(Sprint174 규칙)
- 복사는 `report["report"]`를 그대로 쓴다 — Release Report가 이미
  붙여 넣을 수 있는 글을 만들어 둔다. 여기서 새로 짓지 않는다

라우터는 `GET /api/beta-release-gate` 하나. `test_router_contracts`에
등록한다.

---

## 8. 검증 계획

새 파일 `tests/test_beta_release_gate.py`.

### 8.1 RED 먼저

1. 서비스가 없다 → import 실패
2. `/studio/api/beta-release-gate`가 404
3. 화면에 `배포 확인 정보`가 없다

### 8.2 숫자가 같은가

4. `installations` · `started` · `finished` · `success_rate` ·
   `top_blocked_stage` · `error_kinds` 가 `beta_summary`와 같다
5. readiness의 `checks` · `passed` · `failed` · `unknown`이
   `beta_snapshot`과 같다
6. flow 숫자가 `beta_release_report`의 `funnel`과 같다
7. `taken_at`과 `checked_at`이 같은 시각이다

### 8.3 한 번만 읽는가

8. Gate 한 번에 `beta_dashboard.build`가 **1회** 불린다
   (Sprint192가 쓴 그 방법)

### 8.4 판정하지 않는가

9. 금지 문구 넷이 없다
10. `caution`이 그대로 실려 있다
11. 소스에 셈이 없다 (AST)

### 8.5 남기지 않는가

12. 두 번 불러도 데이터 폴더가 그대로다
13. 새 사건이 생기지 않는다
14. 절대 경로·사용자명·피드백 낱말이 없다

### 8.6 기존 자리가 그대로인가

15. 인자 없이 부른 `beta_snapshot.build()`가 예전과 같다
16. `/api/beta-snapshot`이 그대로 답한다

### 8.7 실측

zip을 새 자리에 풀고 PATH는 System32만 둔 채로, 신규 사용자와 기록
모음 사용자 두 경우를 잰다. 비교할 것은 8.2와 같다.

### 8.8 전체 regression

`fail=0 error=0`. 기준선 4136 + 신규분. 우회 없이.

---

## 9. 완료 조건

- [x] `app/services/beta_release_gate.py` 신규
- [x] `beta_snapshot.build(summary=None)` 주입구 (기존 파일 유일한 변경)
- [x] `GET /api/beta-release-gate` · contract 등록
- [x] `배포 확인 정보` 버튼과 복사
- [x] 숫자 전부 출처와 일치 (아래)
- [x] 기록 읽기 **1회**
- [x] 금지 문구 없음 · caution 유지
- [x] 파일 쓰기 없음 · 새 사건 없음 · 개인정보 없음
- [x] 실측 (신규 / 기록 모음)
- [x] regression `ran=4159 failures=0 errors=0`
- [x] 로컬 커밋까지. **Push 안 함**

### 실측

| | 신규 사용자 | 기록 모음 사용자 |
|---|---|---|
| 설치본 | 1벌 | 4벌 |
| 시작 → 완료 | 1 → 0 (0.0) | 4 → 1 (0.25) |
| 가장 많이 멈춘 곳 | `start` | `workspace_selected` |
| Readiness | O 2 · X 4 · ? 1 | O 4 · X 2 · ? 1 |
| Flow | 1·0·0·0·0 | 4·4·2·1·1 |
| 진단 정보 | O | O |

앞의 자리들과 대조한 일곱 항목이 두 경우 모두 일치했다 — Summary
설치본 · 시작/완료, Readiness O/X/?, Readiness 줄 내용, Flow 숫자,
Snapshot 시각 == Gate 시각, Snapshot 모양 유지.

밖으로 나가도 되는가: 새어 나온 낱말 없음 · 절대 경로 없음 ·
**최종 판단 문구 없음** · 두 번 더 만들어도 데이터 폴더와 기록 그대로 ·
**기록을 읽은 횟수 1회**.

### 겪은 것 하나 — 탐침 낱말이 제 글에 걸렸다

개인정보 검사의 탐침으로 앞선 스프린트들이 쓰던 "사람"을 그대로
가져왔는데, 이 표의 note가 "내보낼지는 사람이 정합니다"라고 말한다.
그 낱말로는 유출과 우리 글을 구별할 수 없다. 탐침을 "홍길동"으로
바꿨다 - 코드가 아니라 테스트가 틀린 경우였다.

탐침은 화면 글에 나올 법하지 않은 것이어야 한다.

---

## 10. 위험과 되돌리기

| 위험 | 판단 |
|---|---|
| 제작 엔진에 영향 | 없음. 읽기만 하는 서비스 하나와 라우터 하나다 |
| `beta_snapshot` 변경이 기존을 깬다 | 기본값이 `None`이라 인자를 안 주면 예전과 같다. 8.6이 지킨다 |
| 화면이 판정하게 된다 | 글은 서버가 짓는다. 화면은 받은 것을 띄우기만 한다 |
| 숫자가 어긋난다 | 기록 1회 읽기 + 출처 대조 테스트 |

되돌리기는 커밋 하나를 `revert`하면 된다.

---

## 11. 범위 밖

- 판정 기준을 늘리는 것. Readiness의 일곱 줄이 전부다
- 새 기록을 모으는 것
- Render Engine · Provider · Pipeline · Free Mode · Upload
