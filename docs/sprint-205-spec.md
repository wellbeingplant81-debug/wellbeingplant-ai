# Sprint205 SPEC — 붙여넣기 칸에서 미리 말한다

- 상태: 완료 (조사 · 구현 · 검증 통과)
- 선행: Sprint204 `d58e5ba`
- 기준선: regression `ran=4219 failures=0 errors=0`
- 결과: regression `ran=4224 failures=0 errors=0` · 화면 +27/-3, 나머지는
  테스트와 이 문서

`app/` 아래에서 바뀐 것은 `static/studio.html` 하나다. 서비스도
라우터도 건드리지 않았다 - 이미 있는 것을 이미 있는 자리에 이었을
뿐이기 때문이다.

---

## 1. 조사 결과 — 검사는 있는데 마법사가 묻지 않는다

세 가지를 확인했다.

### 안내받은 길은 이미 옳다

`script_prompt_builder`는 엔진의 `SCRIPT_PROMPT`를 그대로 준다. 그
프롬프트는 `IMAGE_PROMPT_RULES`를 포함한다 - **Gemini에 그 요청문을
넣고 받은 답을 붙여넣으면 `image_prompt`가 들어 있다.**

즉 안내를 따라간 사람은 애초에 막히지 않는다. 막히는 것은 **제 손으로
쓴 대본이나 다른 데서 가져온 글**을 붙여넣은 사람이다.

### 읽어 보는 검사도 이미 있다

`POST /api/script-check` (Sprint179)가 정확히 그 일을 한다. 고치지
않고 읽고 말한다.

```
Scene 1: 그림 묘사가 없습니다.
hook 이(가) 비어 있습니다. 채팅창에 다시 물어보십시오.
전체가 약 9초로 너무 짧습니다. 목표는 45초입니다.
```

### 그런데 마법사는 그것을 부르지 않는다

```
checkScript('importRaw','importQuality')     <- 있다
checkScript('manualRaw','manualQuality')     <- 있다
wizRaw                                        <- 없다
```

무료 제작 마법사 3단계의 붙여넣기 칸(`wizRaw`)만 그 검사를 쓰지
않는다. 거기 [읽어 보기]는 `/api/production/import`를 부르고, 그것은
**"장면 3개"라고만 말한 뒤 다음으로 보낸다.**

Closed Beta 사용자가 실제로 지나는 길이 하필 그 길이다.

---

## 2. 그래서 사람이 겪는 것

```
1. 붙여넣고 [읽어 보기]      "무릎 통증 완화 스트레칭 · scene 3개"   O
2. [이 대본으로 시작]         프로젝트가 생긴다                       O
3. 내 자료 폴더 고르기        O
4. [제작 시작]                거절 - "Scene 1: 그림 묘사가 없습니다"  X
```

**넷째에서야 안다.** 그런데 그 말은 첫째에서 이미 할 수 있었다.

Sprint203·204가 넷째를 고쳤다면, 이번은 그것을 **첫째로 당긴다.**

---

## 3. 이번에 하는 것

**이미 있는 검사를 이미 있는 자리에 잇는다.** 그뿐이다.

1. 마법사 3단계 [읽어 보기]가 `checkScript('wizRaw','wizQuality')`도
   함께 부른다
2. 결과를 그 자리에 띄운다 - `importRaw`·`manualRaw`가 쓰는 그 함수와
   그 모양 그대로
3. 붙여넣기 칸 옆에 **무엇이 있어야 하는지** 한 줄 적는다

### 셋째의 문구는 어디서 오는가

새 기준을 만들지 않는다. 렌더가 요구하는 것은 이미 한 곳에 적혀 있다.

```python
step01_script_resolve.REQUIRED_SCENE_FIELDS
    = ("scene", "narration", "image_prompt")
```

사람이 읽는 이름은 `script_quality_check`가 이미 쓰고 있다 - "읽을
문장", "그림 묘사". 그 낱말을 그대로 쓴다.

> 장면마다 **읽을 문장**과 **그림 묘사**가 있어야 합니다.
> 위 요청문을 채팅창에 넣고 받은 답이면 둘 다 들어 있습니다.

둘째 줄이 중요하다. 안내받은 길이 이미 옳다는 것을 말해 주면, 손으로
쓰려던 사람이 더 쉬운 길로 돌아갈 수 있다.

---

## 4. 금지 — 지킬 것

- `image_prompt` 자동 생성 없음 · AI 호출 없음
- `script.json` 자동 보정 없음
- Pipeline · Render 수정 없음
- **새 품질 기준 없음.** 무엇이 문제인지는 여전히
  `script_quality_check`가 정한다
- 새 엔드포인트 없음 - `/api/script-check`가 이미 있다

---

## 5. 검증

`tests/test_script_input_contract.py`에 이어 붙인다.

### RED

1. 마법사가 `checkScript`를 부르지 않는다
2. 결과를 띄울 자리(`wizQuality`)가 없다
3. 붙여넣기 칸이 무엇이 필요한지 말하지 않는다

### GREEN

4. 마법사 3단계가 `checkScript('wizRaw','wizQuality')`를 부른다
5. `wizQuality` 자리가 있다
6. 칸 옆에 "읽을 문장"과 "그림 묘사"가 적혀 있다
7. 그 낱말이 `script_quality_check`가 쓰는 낱말과 같다

### 건드리지 않았음

8. `/api/script-check`는 그대로 (읽기만·고치지 않음)
9. 거절 흐름(Sprint203·204) 그대로
10. 갖춘 대본은 그대로 200
11. 검사해도 `script.json`이 생기지 않는다 - 아직 프로젝트가 없다
12. AI를 부르지 않는다

---

## 6. 완료 조건

- [ ] 마법사 3단계에 검사 연결
- [ ] 결과 자리 · 필요한 것 한 줄
- [ ] 새 기준·새 문구·새 엔드포인트 없음
- [ ] regression `fail=0 error=0`
- [ ] 로컬 커밋. **Push 안 함**

---

## 7. 하지 않는 것

- `image_prompt`를 채우는 것
- `/api/production/import`가 무엇을 받아들일지 바꾸는 것.
  파서가 읽는 것과 렌더가 요구하는 것이 다른 것은 사실이고, 그 차이를
  **사람에게 먼저 보여 주는 것**이 이번 일이다. 파서를 조이면 지금
  되는 붙여넣기가 오늘부터 막힌다
