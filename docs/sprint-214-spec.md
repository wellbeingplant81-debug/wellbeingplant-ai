# Sprint214 — 기억과 준비는 다른 것이다

- 상태: 완료 (조사 · 결정 · 구현 · 검증 통과)
- 선행: Sprint213 `bbc4800`
- 기준선: regression `ran=4274 failures=0 errors=0`
- 결과: regression `ran=4283 failures=0 errors=0` · `onboarding_state`
  한 파일 (+21/-1)

RED에서 정확히 둘만 실패했다 - 상태가 안 바뀜, 첫 걸음이 False.
불변 가드 일곱은 처음부터 통과했다. 고칠 것만 고쳤다는 뜻이다.

---

## 1. 먼저 결정 — 조사부터

> 프로젝트 library 연결을 workspace 준비 상태로 인정할 것인가?

### 두 상태가 각각 무엇인가

```python
# free_workspace.py 첫머리
#   1. 폴더를 한 번 정하면 기억한다        remember / remembered
```

`remembered`는 **편의 기억**이다. 라이브러리를 훑는 자리에서 이렇게
쓰인다.

```python
# 라우터 - POST /api/review/{id}/library
if not root:
    root = free_workspace.remembered(_workspace_store())["root"] or ""
    # Sprint152 - 주지 않았으면 정해 둔 폴더를 쓴다.
    #             프로젝트마다 같은 경로를 다시 적게 만들지 않는다.
```

**`root`를 직접 주면 기억은 쳐다보지도 않는다.**

한편 훑은 결과는 프로젝트 안에 남는다.

```python
local_library.save(path, index)      # -> {project}/local_library.json
```

```python
# local_library.load()
"""적어 둔 목록. 없으면 빈 것 - 훑은 적이 없다는 뜻이다."""
```

### 제작이 실제로 무엇을 쓰는가

Sprint213이 답을 이미 냈다. **전역 기억이 비어 있는 채로 영상이 끝까지
나왔다** (`final_short.mp4` · 33.03초 · 작업 `done`).

즉 제작이 기대는 것은 프로젝트의 `local_library.json`이지 전역 기억이
아니다.

### 결정

**인정한다.**

`onboarding_state`가 묻던 것은 "폴더를 골라 두었는가"였는데, 그것은
**준비됐는지를 재는 자가 아니라 편의를 위한 기억**이다. 그 기억이
비었어도 프로젝트가 제 자료 목록을 갖고 있으면, 그 걸음이 하려던 일은
이미 끝나 있다.

**새 기준을 만들지 않는다.** "이 프로젝트에 자료 목록이 있는가"는
`local_library`가 이미 소유한 사실이고, 우리는 그것을 읽을 뿐이다.

---

## 2. 무엇이 어긋났었나

Sprint213 실측.

```
프로젝트에 자료를 이은 뒤
    화면    WORKSPACE_REQUIRED — 내 자료 폴더가 필요합니다
            이어갈 수 있는가  False
    제작    200 · 영상이 나옴
```

같은 사용자의 같은 상태를 화면과 API가 다르게 말했다. 화면을 믿는
사람은 **이미 이어 둔 자료를 두고 또 고르러 간다.**

---

## 3. 고치는 것

`onboarding_state.build()`의 한 줄이다.

```python
 chosen = bool(free_workspace.remembered(store_path).get("root"))
+
+# Sprint214 - 프로젝트가 이미 제 자료 목록을 갖고 있으면 그 걸음은
+# 끝난 것이다. 전역 기억은 "다음에 또 묻지 않기 위한" 편의일 뿐이다.
+if not chosen and project_path:
+    chosen = bool(local_library.load(project_path).get("items"))
```

### 왜 `items`가 있는지를 보는가

`load`는 없으면 빈 것을 돌려준다 - "훑은 적이 없다는 뜻"이라고 그
docstring이 직접 말한다. 그러니 **훑었는가**를 그대로 읽는 것이다.

빈 폴더를 훑은 경우(`items`가 0)는 여전히 준비 안 된 것으로 둔다.
자료가 하나도 없으면 그림도 목소리도 못 고른다.

### 무엇이 바뀌지 않는가

- 프로젝트가 없으면 예전과 같다 (`FIRST_RUN` / `WORKSPACE_REQUIRED`)
- 폴더를 골라 둔 사람도 예전과 같다
- 뒤의 걸음들(대본·품질·final_check)은 손대지 않는다
- **`can_continue`를 새로 정하지 않는다.** 그 값은 상태마다 이미
  정해져 있다

---

## 4. 금지 — 지킬 것

pipeline · render · provider · AI 생성 변경 없음. 고치는 것은
`onboarding_state` 한 곳이다.

---

## 5. 검증

### RED

1. 프로젝트에 자료를 이어 둔 뒤에도 `WORKSPACE_REQUIRED`라고 한다
2. 그런데 제작은 통과한다 (화면과 API가 다른 말)

### GREEN

3. 자료를 이어 두면 그 걸음을 넘어간다
4. 넘어간 뒤 상태가 제작 가능 여부와 어긋나지 않는다

### 건드리지 않았음

5. 프로젝트가 없으면 예전과 같다
6. 폴더를 골라 둔 경우 예전과 같다
7. 빈 목록(훑었지만 자료 0개)은 여전히 준비 안 됨
8. 여섯 걸음의 `자료 연결` 표시가 그 사실을 따라간다

---

## 6. 완료 조건

- [ ] 결정과 근거를 적는다 (1절)
- [ ] `onboarding_state` 한 곳만 고친다
- [ ] 화면과 제작 가능 여부가 같은 말을 한다
- [ ] regression `fail=0 error=0`
- [ ] 로컬 커밋. **Push 안 함**
