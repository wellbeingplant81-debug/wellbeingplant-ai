# Sprint204 SPEC — 거절을 수정 행동으로 잇는다

- 상태: 완료 (조사 · 구현 · 검증 통과)
- 선행: Sprint203 `d4f27aa`
- 기준선: regression `ran=4211 failures=0 errors=0`
- 결과: regression `ran=4219 failures=0 errors=0`

## 겪은 것 — 저장소의 가드가 옳았다

첫 regression에서 14건이 걸렸다. 전부 같은 가드였다.

```python
wired = set(re.findall(r'on(?:click|change)="(\w+)\(', page))
self.assertEqual(sorted(wired - declared), [])
```

`onclick="if(!wizOpen){...}"` 처럼 인라인 코드를 넣었더니 가드가 `if`를
함수 이름으로 읽고 "선언되지 않은 handler"로 판정했다. 같은 가드를
14개 파일이 들고 있어 한꺼번에 걸렸다.

**가드가 맞았다.** onclick 안에 코드를 늘어놓는 것 자체가 이 저장소의
규칙에 어긋난다. 이름 있는 함수 `openScriptFix()`로 뺐고, 덤으로
`scrollIntoView`가 들어가 붙여넣기 칸이 화면 밖에 있어도 보인다.

테스트를 맞추려고 코드를 고친 것이 아니라, 가드가 가리킨 것이 실제
문제였다.

---

## 1. 조사 결과 — Sprint203이 화면을 더 나쁘게 만들었다

솔직히 적는다. 지난 회차에 라우터만 고치고 화면을 보지 않았다.

`studio.html`의 제작 시작 단추는 이렇게 되어 있다.

```js
const r = await fetch("/studio/api/jobs", {method:"POST", ...});
const d = await r.json();
jobId = d.job_id; $("jobState").textContent = "생성 중…";
poll = setInterval(pollJob, 1500);
```

**`r.ok`를 보지 않는다.** 그래서 400이 오면 이렇게 된다.

| | |
|---|---|
| `d.job_id` | `undefined` |
| 화면 글자 | **"생성 중…"** |
| 단추 | `disabled = true` 인 채로 **다시 안 켜진다** |
| 400에 담긴 안내 | **버려진다** |

즉 사람은 **아무 일도 일어나지 않는 화면을 보며 기다린다.**

### 전보다 나빠졌다

| | Sprint203 전 | Sprint203 후 |
|---|---|---|
| 응답 | 200 + job_id | 400 + 안내 |
| 화면 | 몇 초 뒤 "실패: ..." | **"생성 중…" 그대로 멈춤** |
| 단추 | 다시 눌림 | **잠긴 채** |

서버는 더 좋아지고 화면은 더 나빠졌다. 이번에 그것을 잇는다.

---

## 2. 수정 행동이 실제로 있는 자리

`대본 고치기`가 가리키는 곳이 어디인지 확인했다.

```
무료 제작 시작 (wizToggle)
  STEP 3  대본 붙여넣기   <textarea id="wizRaw">
                          [읽어 보기] → [이 대본으로 시작]
```

고친 대본을 다시 붙여넣는 자리가 이미 있다. 새로 만들 것이 없다.

---

## 3. 이번에 하는 것

**세 가지를 잇는다. 새 문구도 새 기준도 만들지 않는다.**

1. 화면이 `r.ok`를 본다
2. 400에 담긴 말(`message` · `reasons` · `next_action`)을 그대로 띄운다
3. 그 자리에서 고치러 갈 수 있게 한다 (무료 제작 3단계로)

### 응답에 한 칸을 더한다 — `state`

화면이 "대본 고치기"라는 **글자를 보고** 무엇을 열지 정하면, 문구가
바뀌는 날 조용히 틀린다.

그래서 `onboarding_state.SCRIPT_CHECK_REQUIRED`라는 **이미 있는 이름**을
함께 싣는다. 화면은 이름을 보고 정한다. 새 판단이 아니라 이미 내린
판단에 이름표를 붙여 보내는 것이다.

```json
{"detail": {
  "state": "SCRIPT_CHECK_REQUIRED",
  "message": "지금 대본으로는 영상을 끝까지 만들 수 없습니다.",
  "reasons": ["Scene 1: 그림 묘사가 없습니다.", ...],
  "next_action": "대본 고치기"
}}
```

---

## 4. 금지 — 지킬 것

- `image_prompt` 자동 생성 없음. **AI provider를 부르지 않는다**
- `script.json`을 고치지 않는다
- render · pipeline 수정 없음
- **새 품질 기준 없음.** 무엇이 문제인지는 여전히
  `script_quality_check`가 정한다

---

## 5. 검증

신규 테스트는 `tests/test_script_input_contract.py`에 이어 붙인다 -
같은 계약을 다루는 자리를 둘로 나누면 다음 사람이 한쪽만 고친다.

### RED

1. 400 응답에 `state`가 없다
2. 화면의 제작 시작 단추가 `r.ok`를 보지 않는다
3. 화면에 거절을 띄우는 자리가 없다

### GREEN

4. 400에 `state == "SCRIPT_CHECK_REQUIRED"`
5. 단추가 `r.ok`를 보고, 실패면 다시 켜진다
6. 화면이 `reasons`를 그대로 띄운다
7. 고치러 가는 단추가 있다

### 건드리지 않았음

8. 갖춘 대본은 그대로 200
9. `project_id` 없는 길 그대로
10. **거절 뒤 `script.json`이 한 바이트도 안 바뀐다**
11. 거절할 때 **provider를 부르지 않는다** (patch로 확인)
12. 렌더가 시작되지 않는다

### 개인정보

13. 400에 절대 경로 없음 · traceback 없음 · 사용자 파일명 없음

---

## 6. 완료 조건

- [ ] 400에 `state` 추가 (이미 있는 이름)
- [ ] 화면이 `r.ok`를 보고 안내를 띄움
- [ ] 단추가 다시 켜짐 · "생성 중…" 오해 없음
- [ ] 고치러 가는 길 연결
- [ ] 자동 생성·자동 수정 없음 (테스트로 고정)
- [ ] regression `fail=0 error=0`
- [ ] 로컬 커밋. **Push 안 함**

---

## 7. 하지 않는 것

- `image_prompt`를 채우는 것
- 새 안내 문구를 짓는 것
- `script_quality_check`의 기준을 손대는 것
