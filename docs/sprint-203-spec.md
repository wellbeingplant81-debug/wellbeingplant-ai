# Sprint203 SPEC — 대본 입력 계약을 제때 말한다

- 상태: 완료 (조사 · 구현 · 검증 통과)
- 선행: Sprint202 `b8c41a1`
- 기준선: regression `ran=4201 failures=0 errors=0`
- 결과: regression `ran=4211 failures=0 errors=0` · diff는 라우터 한
  파일 (+72/-0)

## 사용자가 받는 답이 이렇게 달라졌다

**전**

```
200  {"job_id": "..."}
(몇 초 뒤) 생성 실패: script.json의 scene이 뒤 단계가 요구하는 값을
          갖추지 못했습니다 - scene 1: image_prompt 없음
```

**후**

```
400  지금 대본으로는 영상을 끝까지 만들 수 없습니다.
       - hook 이(가) 비어 있습니다. 채팅창에 다시 물어보십시오.
       - character 이(가) 비어 있습니다. 채팅창에 다시 물어보십시오.
       - Scene 1: 그림 묘사가 없습니다.
       - Scene 2: 그림 묘사가 없습니다.
       - 전체가 약 6초로 너무 짧습니다. 목표는 45초입니다.
     다음 행동: 대본 고치기
```

새 문구를 하나도 만들지 않았다. 화면이 쓰던 말을 그대로 옮겼다.

---

## 1. 조사 결과 — 안내는 이미 있다

Sprint202에서 렌더가 개발자 문구로 죽었다.

> `script.json의 scene이 뒤 단계가 요구하는 값을 갖추지 못했습니다 -
> scene 1: image_prompt 없음`

그래서 "사람이 읽을 말을 만들어야 한다"로 시작했는데, **이미 있었다.**

### 흐름과 각 자리가 아는 것

```
붙여넣기  chat_script_parser.parse_script()
              -> narration 은 만든다.  image_prompt 는 만들지 않는다
                 (실측: scene 1·2 모두 image_prompt 없음)

계약      step01_script_resolve.REQUIRED_SCENE_FIELDS
              = ("scene", "narration", "image_prompt")
              validate() 가 여기서 막는다 (개발자 문구)

안내      script_quality_check.check()
              -> "Scene 1: 그림 묘사가 없습니다."      <- 사람 말이 이미 있다
                 "hook 이(가) 비어 있습니다..."
                 "전체가 약 9초로 너무 짧습니다..."

화면      onboarding_state.build(store, project)
              폴더 고르기 전  WORKSPACE_REQUIRED
              폴더 고른 뒤    SCRIPT_CHECK_REQUIRED
                              "대본을 고쳐야 합니다"
                              "지금 대본으로는 영상을 끝까지 만들 수 없습니다."
                              다음 행동: 대본 고치기
                              can_continue: False
                              이유에 "Scene 1: 그림 묘사가 없습니다" 그대로
```

### 그래서 답은

> **사용자가 어느 화면에서 무엇을 해야 하는지 알 수 있는가?**
>
> **화면을 따라간다면 알 수 있다.** 폴더를 고른 뒤 화면이 "대본을
> 고쳐야 합니다"라고 말하고, 어느 Scene의 무엇이 없는지까지 적는다.

새 안내를 만들면 **같은 말을 두 벌 갖게 된다.** 그것이 이 저장소가
여러 번 겪은 사고다.

---

## 2. 진짜 구멍 — 문지기가 화면에만 있다

```
POST /api/jobs 가 부르기 전에 보는 것:
    X  script_quality_check
    X  validate
    X  onboarding_state
    X  final_check
    X  resolve
```

**아무것도 보지 않는다.** 화면이 버튼을 감출 뿐이고, 그 아래 API는
누구에게나 열려 있다. Sprint202의 smoke test가 정확히 그 틈으로
들어가 렌더까지 갔다.

그 결과가 이렇다.

| | 화면을 따라간 사람 | API를 직접 부른 사람 |
|---|---|---|
| 언제 안다 | 제작 시작 전 | **몇 초 뒤 실패로** |
| 무슨 말을 듣는다 | "Scene 1: 그림 묘사가 없습니다" | **`image_prompt 없음`** |
| 다음 행동 | "대본 고치기" | **없음** |

같은 프로그램이 같은 상태를 두 가지로 말한다.

---

## 3. 이번에 하는 것

**막는 자리를 화면 아래로 한 칸 내린다.** 새 말을 만들지 않는다.

```
POST /api/jobs
    project_id 가 있으면 (= 미리 놓인 대본을 쓰는 길)
        -> 렌더 계약을 먼저 본다
        -> 못 갖췄으면 400 으로 돌려준다
           그때 하는 말은 script_quality_check 가 이미 만든 그 말
```

### 무엇으로 막는가 — 계약이지 품질이 아니다

두 후보가 있다.

| | 막는 기준 | 문제 |
|---|---|---|
| script_quality_check | 화면이 쓰는 것 | "9초로 짧습니다"처럼 **렌더가 견디는 것도 막는다** |
| **resolver.validate** | 렌더가 실제로 요구하는 것 | 없음 |

**후자로 막는다.** 어차피 죽었을 것만 더 일찍, 더 또렷하게 막는다.
멀쩡한 대본이 오늘부터 막히는 일은 없다.

### 무엇으로 말하는가 — 이미 있는 말

막는 기준은 계약이지만, 사람에게 하는 말은 `script_quality_check`가
이미 만든 문장을 그대로 쓴다. 새 문구를 지으면 화면과 API가 다른
낱말로 같은 것을 말하게 된다.

```
막을지 말지  step01_script_resolve.validate()
무슨 말을    script_quality_check.check()["reasons"]
다음 행동    onboarding_state 의 그 말 ("대본 고치기")
```

### AUTO 경로는 건드리지 않는다

`project_id` 없이 부르면 예전과 완전히 같다. 그 길은 AI가 대본을
쓰는 길이고, 아직 없는 대본을 미리 검사할 수 없다.

---

## 4. 금지 — 지킬 것

- render engine · provider · pipeline 수정 없음. **라우터 한 곳**
- image 생성 로직 없음
- **자동 보정 없음.** `image_prompt`를 지어 넣지 않는다. 사용자가
  준 대본을 우리가 고치면 그것은 더 이상 사용자가 준 대본이 아니다
  (`ScriptResolveError`의 docstring이 이미 그렇게 적혀 있다)
- 테스트 통과용 데이터 삽입 없음
- 새 판단 기준 없음 — 막는 것도 말하는 것도 이미 있는 자리가 정한다

---

## 5. 검증

신규 `tests/test_script_input_contract.py`.

### RED

1. `image_prompt` 없는 대본으로 `POST /api/jobs` → 지금은 **200**이고
   job이 만들어진다 (막는 자리가 없다)
2. 그 job이 나중에 개발자 문구로 죽는다
3. 응답에 사용자가 할 다음 행동이 없다

### GREEN

4. 같은 요청이 **400**으로 돌아온다
5. 그 답에 `Scene 1: 그림 묘사가 없습니다`가 있다
   (= `script_quality_check`가 만든 그 문장)
6. 다음 행동 문구가 있다
7. **job이 만들어지지 않는다** (기록도 남지 않는다)

### 건드리지 않았음

8. `project_id` 없이 부르면 예전과 같다 (200)
9. 갖춘 대본은 그대로 통과한다 (200)
10. `image_prompt`를 지어 넣지 않는다 — 거절 뒤 script.json이 그대로
11. 렌더 산출물에 영향 없음 (파이프라인 코드 diff 0)

### 개인정보

12. 400 응답에 절대 경로 없음 · traceback 없음
13. **사용자 파일명 노출 여부** — 프로젝트 폴더 이름·자료 파일 이름이
    답에 실리지 않는지 본다

---

## 6. 완료 조건

- [ ] `POST /api/jobs` 문지기 (미리 놓인 대본 경로만)
- [ ] 말은 `script_quality_check`가 만든 것 그대로
- [ ] AUTO 경로 불변 · 갖춘 대본 불변
- [ ] 자동 보정 없음 · job 안 만들어짐
- [ ] 개인정보 없음
- [ ] regression `fail=0 error=0`
- [ ] 로컬 커밋. **Push 안 함**

---

## 7. 이번에 하지 않는 것

- **`image_prompt`를 자동으로 채우는 것.** 붙여넣기 경로가 그것을
  만들지 않는 것이 옳은지는 따로 정할 일이다. 채우려면 무엇을 보고
  채울지 정해야 하고 그것은 새 판단이다
- 화면 문구 변경. 이미 맞는 말을 하고 있다
- `script_quality_check`의 기준 변경
