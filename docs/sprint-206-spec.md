# Sprint206 SPEC — 적히는데 아무도 안 세는 걸음

- 상태: 완료 (조사 · 구현 · 검증 통과)
- 선행: Sprint205 `d2ce878`
- 기준선: regression `ran=4224 failures=0 errors=0`
- 결과: regression `ran=4239 failures=0 errors=0` · 세는 쪽 3파일
  (+44/-12)

## 갱신한 옛 테스트 하나

Sprint200의 `test_the_assets_step_says_it_does_not_know`는 그때의
사실을 적어 둔 것이었다 - 수가 없었고, 없는 이유가 "세는 자리가
없어서"였다. 그 사실이 이번에 바뀌었으므로 이름과 내용을 고쳤다.

**여전히 중요한 것은 그대로 뒀다** - `ok is None`. 수가 생겼다고
판정이 생긴 것은 아니다.

---

## 1. 질문에 먼저 답한다

> **현재 데이터로 "사용자가 어느 단계에서 멈췄는가" 말할 수 있는가?**

**네 칸은 말할 수 있고, 다섯째 칸은 말할 수 없다.**

```
beta_dashboard.STAGES
    start                 켜기만 하고 아무것도 안 함
    workspace_selected    폴더까지 고르고 멈춤
    script_ready          대본까지 넣고 멈춤
    render_started        만들기 시작하고 멈춤
    done                  끝까지 감
```

`blocked_stage`가 이 다섯으로 세고, `top_blocked_stage`가 가장 많은
칸을 말한다. 화면도 그것을 띄운다(`studio.html:4431`). 여기까지는
이미 된다.

### 빠진 칸 — 자료 준비

`beta_telemetry`가 아는 사건은 여섯이다.

```
workspace_selected · script_ready · preparation_ready
render_started · render_completed · render_failed
```

`preparation_ready`는 **실제로 적힌다.**

```python
# app/routers/studio.py:1950
if found.get("state") == "ready":
    beta_telemetry.note(beta_telemetry.PREPARATION_READY, once=project_id)
```

그런데 세는 쪽 셋 어디에도 없다.

```python
ORDER    = (workspace_selected, script_ready, render_started, render_completed)
STAGES   = (start, workspace_selected, script_ready, render_started, done)
COUNTED  = (workspace_selected, script_ready, render_started,
            render_completed, render_failed)
```

**모든 사용자의 기록에 들어 있는데 아무도 읽지 않는 숫자다.**

### 그래서 지금 무슨 일이 벌어지는가

대본까지 넣은 사람 둘이 있다고 하자.

| | 실제로 한 일 | 지금 뭐라고 세는가 |
|---|---|---|
| 갑 | 대본 넣고 그만둠 | `script_ready`에서 멈춤 |
| 을 | 자료까지 다 갖추고 제작 직전에 그만둠 | **`script_ready`에서 멈춤** |

둘이 같은 칸에 들어간다. **자료를 못 모아서 못 간 사람과, 다 모아
놓고 안 누른 사람을 구별할 수 없다.** 고칠 곳이 전혀 다른데도.

Sprint200이 RC 카드 다섯째 걸음을 `?`로 둔 이유가 이것이다.

---

## 2. 이번에 하는 것 — 세기만 한다

**이미 적혀 있는 것을 센다.** 새로 모으지 않는다.

```python
COUNTED = (..., preparation_ready, ...)      # 이 한 줄
```

그리고 Sprint200이 `?`로 비워 둔 자리를 채운다.

```
전  ? 5. 이미지·음성 자료
       자료가 갖춰졌다는 기록은 남지만 모아 세는 자리가 없어 아직 모릅니다.

후  ? 5. 이미지·음성 자료  2벌
       자료가 갖춰진 기록 2벌. 갖췄는지 판정하는 자리는 없습니다.
```

**`ok`는 여전히 `?`다.** 숫자가 생겼다고 판정이 생긴 것은 아니다 -
"몇 벌이 거기까지 갔다"와 "그것으로 충분한가"는 다른 말이고, 후자를
판정하는 자리는 여전히 없다.

---

## 3. 하지 않는 것 — 그리고 왜

### `ORDER`·`STAGES`에 넣지 않는다

넣으면 `blocked_stage` 바구니가 달라진다. 어제까지 `script_ready`에서
멈춘 것으로 세어지던 사람이 오늘부터 `preparation_ready`로 옮겨간다.

그것은 **이미 내려진 판정을 바꾸는 일**이다. 더 정확해지는 것은
맞지만, 이번 지시의 "새로운 성공 기준 추가 금지"가 지키려는 자리가
바로 거기다. 지난 회차들에서 배운 대로 - 판정을 바꾸는 것은 따로
승인받을 일이다.

**그래서 이번에는 갑과 을을 여전히 구별하지 못한다.** 다만 "자료까지
간 기록이 몇 벌인지"는 이제 말할 수 있고, 그 둘의 차이는 그 숫자로
짐작할 수 있다.

### `beta_funnel.STEPS`에도 넣지 않는다

funnel은 칸 사이의 낙차로 `irregular`를 판정한다. 칸을 끼워 넣으면
그 낙차가 전부 달라진다 - 같은 이유로 하지 않는다.

### 무엇을 하면 구별되는가 (다음 승인 사항)

`ORDER`와 `STAGES`에 `preparation_ready`를 넣는 것. 그러면 바구니가
여섯이 되고 갑과 을이 갈린다. 대신 그 전에 쌓인 기록의 해석이
달라진다는 것을 알고 해야 한다.

---

## 4. 금지 — 지킬 것

- **새 기록 수집 없음.** 이미 적히는 사건을 셀 뿐이다
- **새 이벤트 없음.** `beta_telemetry.EVENTS`를 건드리지 않는다
- **새 성공 기준 없음.** `ok`는 `?` 그대로
- AI 호출 · script 생성 · image_prompt 생성 · render · pipeline 수정 없음
- 개인정보 저장 없음 - 세는 것은 사건 이름의 개수뿐이다

---

## 5. 검증

### RED

1. `beta_dashboard.build()`에 `preparation_ready`가 없다
2. RC 카드 다섯째 걸음의 `count`가 `None`이다

### GREEN

3. 대시보드가 `preparation_ready`를 센다
4. 그 수가 기록에 적힌 그대로다 (2벌 넣으면 2)
5. RC 카드 다섯째가 그 수를 보여 준다
6. **`ok`는 여전히 `None`** - 숫자가 판정이 되지 않는다

### 건드리지 않았음

7. `blocked_stage`가 예전과 같다 (바구니 다섯 그대로)
8. `top_blocked_stage`가 예전과 같다
9. `beta_funnel`의 칸이 다섯 그대로
10. `success_rate`가 예전과 같다
11. `beta_telemetry.EVENTS` 그대로

### 남기지 않는다

12. 두 번 불러도 데이터 폴더가 그대로
13. 새 사건이 생기지 않는다
14. 절대 경로 · 사용자명 없음

---

## 6. 완료 조건

- [ ] `COUNTED`에 한 줄
- [ ] RC 다섯째 걸음에 실제 수 · `ok`는 `?`
- [ ] 판정하는 자리 넷(ORDER · STAGES · funnel · success_rate) 불변
- [ ] regression `fail=0 error=0`
- [ ] 로컬 커밋. **Push 안 함**
