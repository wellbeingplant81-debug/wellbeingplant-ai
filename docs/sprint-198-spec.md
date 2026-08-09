# Sprint198 SPEC — 실패 메시지의 경로 가리기

- 상태: 완료 (승인 · 마스킹만 · 검증 통과)
- 선행: Sprint195 `674fca6`, Sprint196 `894c23e`, Sprint197 `18d1619`
- 기준선: regression `ran=4121 failures=0 errors=0`
- 결과: regression `ran=4136 failures=0 errors=0`

승인 시 7.1은 **A**(return code 안 넣음), 7.2도 **A**(배너 안 자름)로
확정됐다. 이번은 가리기만 한다.

6.3의 "새 파일 `app/utils/path_masking.py`"는 승인 범위가 "studio_jobs
표시 경계에서만"으로 좁혀지면서 **`studio_jobs` 안의 `_masked()`로**
바뀌었다. 바뀐 파일은 그 하나뿐이다.

---

## 1. 목표

렌더가 실패했을 때 화면에 뜨는 글에서 사용자 이름과 절대 경로를
지우고, 왜 실패했는지는 그대로 남긴다.

Sprint197이 **성공·실패 가리지 않고 상시로 찍히던 것**을 없앴다면,
이번은 **실패했을 때만 뜨는 것**이다.

---

## 2. 실측 — 지금 화면에 무엇이 뜨는가

`studio_jobs._run`을 그대로 통과시켜 쟀다. 한글 주제 폴더에서 실제
ffmpeg를 실패시킨 결과다.

```
state  failed

[job["error"]]   15줄        <- 화면: "실패: " + d.error
  홈 경로          2줄
  사용자명         2줄
  절대 경로 전체    2줄

[job["console"]] 44줄
  홈 경로          5줄
  사용자명         5줄
  프로젝트 경로     2줄       <- traceback.format_exc()
  절대 경로 전체    7줄
```

실제로 뜨는 줄들이다.

```
[concat @ ...] Impossible to open 'C:\Users\baeku\AppData\Local\Temp\...\무릎 통증 완화 스트레칭\...'
Error opening input file C:\Users\baeku\AppData\Local\Temp\...\scene_audio_list.txt
File "C:\Projects\wellbeingplant-ai\cloud-run\app\services\audio_service.py", line 94, in concat_scene_audio
File "C:\Projects\wellbeingplant-ai\cloud-run\app\services\studio_jobs.py", line 237, in _run
```

---

## 3. 지시받은 범위보다 새는 곳이 넓다

의뢰는 `job["error"]`를 지목했다. 실측은 **Console 쪽이 더 크다**고
말한다 — 절대 경로가 그쪽은 7줄, error는 2줄이다.

차이는 `traceback.format_exc()`다. 예외 메시지만 가리면
**프로젝트 절대 경로(`C:\Projects\wellbeingplant-ai\...`)는 그대로
남는다.** 의뢰의 "제거: 절대 프로젝트 경로"가 지켜지지 않는다.

그래서 이 SPEC은 **둘 다** 대상으로 잡는다.

| | 지금 | 목표 |
|---|---|---|
| `job["error"]` | 절대 경로 2줄 | 0줄 |
| `job["console"]`의 실패 부분 | 절대 경로 7줄 | 0줄 |

---

## 4. 어디에 거는가 — raise 자리가 아니라 표시 경계

의뢰의 정책 예시는 예외 자체를 바꾸는 모양이다.

```python
Exception("ffmpeg error <user_path>\\file.mp4")
```

그렇게 하려면 예외를 던지는 자리를 고쳐야 하는데, 그 자리가
`audio_service` · `final_video_service` · `duration_optimizer` ·
`asset_integration_service` · `elevenlabs_provider` · `voice_import`
이다. **금지 목록의 Render Engine과 Provider 그 자체다.**

표시 경계에 걸면 한 모듈로 끝난다.

```python
# studio_jobs 의 except 넷
_append_line(job_id, f"[Studio] 생성 실패: {safe(str(exc))}")
_append_line(job_id, safe(traceback.format_exc()))
job["error"] = safe(str(exc))
```

이 편이 나은 이유가 셋이다.

1. **금지된 파일을 하나도 건드리지 않는다**
2. **traceback까지 덮는다.** raise 자리를 고쳐도 traceback은 못 막는다
3. **어디서 온 예외든 덮는다.** 앞으로 새 예외가 생겨도 자동으로 걸린다

예외 객체 자체는 원문을 그대로 들고 있다. 로그·터미널에서는 여전히
전체 경로를 볼 수 있고, 화면에만 가려진 글이 간다. **보는 사람이
다르면 보이는 것도 달라야 한다**는 뜻에서 이쪽이 맞다.

완료 조건(`job["error"]` 절대 경로 없음)은 이 방식으로 그대로
충족된다.

---

## 5. 함정 — `_append_line`에 걸면 안 된다

가장 짧아 보이는 자리가 `_append_line`이다. 거기 걸면 안 된다.

```python
if job["project_path"] is None and line.startswith(_PROJECT_LINE):
    job["project_path"] = line[len(_PROJECT_LINE):].strip()
```

Console로 들어오는 `Project : C:\...\output\...` 한 줄에서 작업
디렉터리를 뽑아낸다. 여기서 먼저 가려 버리면 `job["project_path"]`가
`<user_path>\...`가 되고, **진행률 표시가 조용히 죽는다.**

그래서 마스킹은 except 블록 넷에만 명시적으로 건다.

---

## 6. 가리는 방법

### 6.1 아는 접두사를 먼저 바꾼다

| 무엇 | 어디서 얻나 | 바뀌는 모양 |
|---|---|---|
| 사용자 홈 | `os.path.expanduser("~")` | `<user_path>` |
| 내 자료 폴더 | `runtime_paths.home()` | `<data_path>` |
| 프로그램 자리 | `runtime_paths.program_dir()` · `bundle_root()` | `<app_path>` |

**사용자 이름은 홈 경로 안에만 있다.** 접두사를 바꾸면 "사용자명
없음"이 정확히 달성된다. 정규식으로 이름을 찾아다니지 않는다 - 이름은
어디에나 있을 수 있는 글자라 찾아다니면 엉뚱한 것을 지운다.

긴 접두사부터 바꾼다. `runtime_paths.home()`이 홈 아래에 있으므로,
짧은 것을 먼저 바꾸면 긴 것이 영영 안 걸린다.

### 6.2 남은 절대 경로는 백스톱으로

다른 드라이브(`D:\media\...`)나 아직 모르는 자리를 위해 드라이브
문자로 시작하는 경로를 한 번 더 훑는다.

**여기서 조심할 것이 있다.** 이 저장소의 경로에는 공백이 있다.

```
C:\Users\baeku\...\무릎 통증 완화 스트레칭\audio\scene_audio_list.txt
```

`\S+`로 끊으면 `무릎`까지만 지우고 `통증 완화 스트레칭\audio\...`가
남는다. 지운 것도 아니고 안 지운 것도 아닌 상태가 된다.

그래서 백스톱은 **줄 끝이나 따옴표까지** 먹는 쪽으로 잡고, 마지막
조각(파일 이름)만 남긴다. 의뢰의 정책 그대로다.

```
Error opening input file <path>\scene_audio_list.txt
```

### 6.3 어디에 두는가

`app/utils/path_masking.py` (새 파일). 순수 문자열 함수다 -
프로세스도 파일도 건드리지 않으므로 테스트가 직접 부를 수 있다.
`app/utils`에는 이미 `atomic_write` · `asset_cache` · `subtitle_utils`가
같은 성격으로 있다.

---

## 7. 결정이 필요한 것 둘

### 7.1 return code — 지금 없다

의뢰의 "유지" 목록에 `return code`가 있다. 그런데 지금 `job["error"]`
에는 return code가 **없다**. `raise Exception(result.stderr)`가
stderr만 담기 때문이다.

즉 이것은 유지가 아니라 **추가**다. 그리고 추가하려면 raise 자리를
고쳐야 하는데 그 자리가 금지 목록이다.

| | |
|---|---|
| **A. 넣지 않는다 (권고)** | 이번 범위는 가리기다. rc는 별도 |
| B. 넣는다 | Render Engine·Provider 수정 승인이 따로 필요 |

### 7.2 ffmpeg 배너 13줄 — 자를 것인가

`job["error"]` 15줄 중 쓸모 있는 것은 마지막 2줄이다. 나머지는
ffmpeg 버전·컴파일 옵션·libav 버전이다.

```
ffmpeg version 7.1-essentials_build-www.gyan.dev Copyright (c) 2000-2024
  built with gcc 14.2.0 (Rev1, Built by MSYS2 project)
  configuration: --enable-gpl --enable-version3 ...
  libavutil      59. 39.100 / 59. 39.100
  ... (13줄)
Error opening input file <path>\scene_audio_list.txt      <- 이것만 쓸모 있다
```

의뢰의 허용에 "ffmpeg 오류 원문 중 **필요한 부분** 유지"가 있어 자르는
것도 범위 안이다.

| | 내용 | 위험 |
|---|---|---|
| **A. 가리기만 (권고)** | 15줄 그대로, 경로만 가림 | 없음. 원인이 확실히 남음 |
| B. 뒷부분 N줄만 | 화면이 읽을 만해짐 | 자르는 규칙이 틀리면 원인을 잃는다 |

**A를 권한다.** 이번 스프린트의 목적은 가리기이고, 자르기는 "원인을
잃지 않는가"를 따로 재야 한다. 다만 이번에 **노이즈 줄 수를 측정해
보고**하고, 그것으로 다음 판단의 근거를 남긴다.

---

## 8. 검증 계획

새 파일 `tests/test_path_masking.py` (함수 자체) 와
`tests/test_render_error_exposure.py` (화면까지의 길).

### 8.1 RED 먼저

1. **한글 사용자 경로가 error에 뜬다** — 한글 주제 폴더에서 진짜
   ffmpeg를 실패시키고, `job["error"]`에 홈 경로·사용자명이 있는지
2. **절대 경로가 뜬다** — `job["error"]`와 `job["console"]` 둘 다
   드라이브 문자 경로를 세어 0이 아닌지
3. **프로젝트 경로가 뜬다** — traceback의 `C:\Projects\...`

셋 다 지금은 실패해야 한다(= 노출이 실제로 있다).

### 8.2 GREEN

4. **예외 종류가 같다** — `Exception`. 마스킹은 표시 경계에서만
   하므로 올라가는 예외 객체 자체는 그대로다
5. **실패 원인이 남는다** — `Error opening input file`이 여전히 있다
6. **파일 이름은 남는다** — `scene_audio_list.txt`
7. **`Project :` 추출이 안 깨진다** — 5절의 함정. 정상 렌더에서
   `job["project_path"]`가 마스킹되지 않은 진짜 경로인지
8. **성공 렌더 산출물 sha256 불변** — Sprint196·197과 같은
   `git stash` 비교

### 8.3 함수 자체 (순수 함수라 빠르게 여러 모양)

9. 홈·데이터·프로그램 접두사가 각각 제 태그로 바뀐다
10. 긴 접두사가 먼저 바뀐다 (짧은 것이 긴 것을 먹지 않는다)
11. 공백이 든 한글 경로가 통째로 가려진다
12. 파일 이름은 남는다
13. 경로가 없는 글은 그대로 나온다 (건드리지 않는다)
14. 여러 경로가 한 줄에 있어도 다 가려진다

### 8.4 전체 regression

`fail=0 error=0`. 기준선 4121 + 신규분. 우회 없이.

---

## 9. 완료 조건

- [x] `job["error"]`에 절대 경로 0줄 · 사용자명 0줄
- [x] `job["console"]`의 실패 부분(예외 메시지 + traceback)도 0줄
- [x] 실패 원인 문구와 파일 이름이 남음
- [x] 예외 종류 불변 (`Exception`) · 예외 객체는 원문 유지
- [x] `job["project_path"]` 추출 정상 (마스킹되지 않음)
- [x] 성공 렌더 산출물 sha256 불변
- [x] 배너 노이즈 줄 수 측정치 보고 (아래)
- [x] regression `ran=4136 failures=0 errors=0`
- [x] 로컬 커밋까지. **Push 안 함**

### 실측 (`studio_jobs._run`을 그대로 통과시킨 실패 job)

| | 수정 전 | 수정 후 |
|---|---|---|
| `job["error"]` 절대 경로 | 2줄 | **0줄** |
| `job["error"]` 홈 경로 · 사용자명 | 2줄 · 2줄 | **0줄 · 0줄** |
| `job["console"]` 절대 경로 | **7줄** | **0줄** |
| `job["console"]` 프로젝트 경로 | 2줄 | **0줄** |
| 실패 원인 문구 | 있음 | 있음 |
| `concat_scene_audio` sha256 | `648e5f87e64b0d78` | 같음 |
| `merge_video_audio` sha256 | `973ed50d463f16c4` | 같음 |

가려진 모양은 정책 그대로다.

```
전  Error opening input file C:\Users\baeku\무릎 통증 완화 스트레칭\audio\scene_audio_list.txt.
후  Error opening input file <user_path>\scene_audio_list.txt.
```

### 배너 노이즈 — 7.2를 다시 볼 때의 근거

`job["error"]` 15줄 중 쓸모 있는 것은 마지막 2줄이다. 나머지 13줄
(87%)은 ffmpeg 버전·컴파일 옵션·libav 버전이다. 이번에는 자르지
않기로 했으므로 숫자만 남긴다.

### 겪은 것 하나 — PowerShell이 BOM을 넣었다

네 곳의 요약 줄을 `-replace`로 고치면서 `Set-Content -Encoding utf8`을
썼고 그것이 BOM을 넣었다. 파이썬은 읽지만 도구에 따라 첫 줄이
어긋난다. 바로 확인해 지웠고, 파일 끝 개행과 개행 코드 혼입도 함께
봤다(107 추가 / 12 삭제 - 줄 수가 그대로이므로 개행은 안 바뀌었다).

`.py`는 PowerShell로 쓰지 않는다.

---

## 10. 위험과 되돌리기

| 위험 | 판단 |
|---|---|
| 렌더 결과가 달라진다 | 불가능. 표시 경계만 고친다 |
| 원인을 잃는다 | 가리기만 하고 자르지 않는다(7.2 A). 문구는 그대로 |
| 진행률이 죽는다 | 5절의 함정. `_append_line`에 걸지 않고 테스트로 고정 |
| 마스킹이 과해서 읽을 수 없어진다 | 파일 이름을 남긴다. 테스트로 고정 |
| 예외 객체가 바뀐다 | 안 바뀐다. 표시할 때만 가린다 |

되돌리기는 커밋 하나를 `revert`하면 된다.

---

## 11. 범위 밖

- **`Project :` 줄의 경로.** 사용자가 제 작업 폴더를 찾으라고 일부러
  보여 주는 것이다. 가리면 기능이 사라진다
- **로그·터미널의 원문.** 개발자가 보는 자리다. 가리는 것은 화면뿐
- **예외를 던지는 자리들.** Render Engine·Provider라 금지 목록이다.
  표시 경계에서 덮으므로 고칠 이유도 없다
- **return code 추가 (7.1 B)** · **배너 자르기 (7.2 B)** — 지시가
  있으면 포함한다
