# Sprint196 SPEC — production subprocess encoding 안정화

- 상태: 완료 (승인 · 10곳 전체 구현 · 검증 통과)
- 선행: Sprint194 `684e187`, Sprint195 `674fca6`
- 기준선: regression `ran=4109 failures=0 errors=0`
- 결과: regression `ran=4112 failures=0 errors=0` (우회 없이)

승인 시 등급 B 3곳 포함으로 결정되어 10곳 전부 고쳤다. 원장
(`LEFT_IN_APP`)은 비었다.

---

## 1. 목표

`app/` 안에서 ffmpeg/ffprobe를 부르고 그 출력을 받아 두는 **10곳**이,
자식이 낸 말을 어떤 글자로 읽을지 밝히지 않는다. 그래서 자식이 한글을
내는 순간 읽는 스레드가 죽고 `stdout`/`stderr`가 `None`이 된다.

이 스프린트는 **읽는 방법만** 고친다. 무엇을 만들지는 한 글자도 바꾸지
않는다.

---

## 2. 왜 지금인가 — 실측 근거

Sprint195에서 "잠재 위험"으로 분류하고 넘겼다. 그 판단이 틀렸다.
production과 똑같은 방식으로 불러 본 결과다.

```
PYTHONIOENCODING  utf-8:surrogateescape     <-- 이 환경에 이미 걸려 있다
로케일 인코딩      cp949                     <-- text=True가 쓰는 값

한글 없는 경로
  ffmpeg  무음 만들기        rc=0  stdout=0자  stderr=2244자
  ffprobe 길이 (-v error)   rc=0  stdout=9자  stderr=0자

한글 경로
  ffmpeg  무음 만들기        rc=0  stdout=0자  stderr=None   <-- 죽었다
  ffprobe 길이 (-v error)   rc=0  stdout=9자  stderr=0자

한글 경로 + 실패
  ffprobe 없는 파일          rc=1           stderr=None   <-- 죽었다
  ffmpeg  없는 파일          rc=4294967274  stderr=None   <-- 죽었다
```

자식이 낸 바이트를 그대로 보면 이유가 분명하다.

```
b'...\\\xeb\xac\xb4\xeb\xa6\x8e \xed\x86\xb5\xec\xa6\x9d\\...wav: Illegal byte sequence'
  utf-8로 읽힌다   O
  cp949로 읽힌다   X  (illegal multibyte sequence, position 53)
```

ffmpeg와 ffprobe는 경로를 **UTF-8로** 쓴다. `text=True`는 그 사실을
모르고 로케일(cp949)로 읽는다. 이 머신에서 둘은 언제나 다르다.

**가장 나쁜 점은 조용하다는 것이다.** `subprocess.run`은 예외를 내지
않는다. 읽는 스레드만 죽고, 호출한 쪽은 `None`을 쥔 채 정상인 줄 안다.

### 언제 드러나는가

주제명이 폴더 이름이 되는 자리가 실제로 있다. `무릎 통증 완화
스트레칭` 같은 프로젝트를 만드는 순간, 그 경로가 ffmpeg의 로그에
실린다. 즉 **평범한 한국어 주제 하나면 조건이 갖춰진다.**

---

## 3. 범위 — 10곳

`app/` 안의 `subprocess.run(..., capture_output=True, text=True)` 중
`encoding`을 주지 않은 전부. Sprint195의 `LEFT_IN_APP` 원장과 같다.

출력을 **어떻게 쓰는지**가 피해의 크기를 가른다.

### 등급 A — 실패 이유를 잃는다 (7곳)

`result.stderr`를 예외 메시지에 담는다. 렌더가 깨진 그 순간,
`Exception(None)`이 올라간다. **무엇이 잘못됐는지 알 길이 사라진다.**

| # | 위치 | 쓰임 |
|---|---|---|
| 1 | `app/services/audio_service.py:70` | `print` 2회 + `raise Exception(result.stderr)` |
| 2 | `app/services/audio_service.py:147` | `print` 2회 + `raise Exception(result.stderr)` |
| 3 | `app/services/final_video_service.py:108` | `print` 2회 + `raise Exception(result.stderr)` |
| 4 | `app/services/duration_optimizer.py:93` | `raise Exception(result.stderr)` |
| 5 | `app/services/duration_optimizer.py:115` | `raise Exception(result.stderr)` |
| 6 | `app/services/asset_integration_service.py:241` | `raise Exception(f"...: {result.stderr}")` |
| 7 | `app/providers/elevenlabs_provider.py:142` | `raise Exception(f"...: {result.stderr}")` |

1~3은 `print(result.stdout)` / `print(result.stderr)`도 한다. 지금
조건에서는 화면에 `None`이 찍힌다.

### 등급 B — 오늘은 무사하다 (3곳)

| # | 위치 | 쓰임 | 왜 무사한가 |
|---|---|---|---|
| 8 | `app/services/duration_optimizer.py:49` | `result.stdout.strip()` → `float` | `-of default=...`라 stdout은 숫자뿐 · ASCII |
| 9 | `app/services/technical_validation_service.py:25` | `result.stdout.strip()` → `float` | 같음 |
| 10 | `app/production/providers/voice_import.py:114` | `returncode`만 본다 | `stdout`/`stderr`를 아예 안 읽는다 |

**무사한 것과 안전한 것은 다르다.** 셋 다 같은 방식으로 부르고 있어서,
누가 `-v` 값이나 `-of` 형식을 바꾸는 날 그대로 A가 된다. 8·9는
그때 `None.strip()`으로 죽고, 10은 계속 조용할 것이다.

---

## 4. 금지사항과 그 해석

| 금지 | 이 스프린트에서 지키는 방법 |
|---|---|
| 렌더 로직 변경 | 명령 배열(`command`)을 만드는 코드는 한 글자도 건드리지 않는다. ffmpeg에 넘어가는 인자가 바뀌면 안 된다 |
| Provider 동작 변경 | `elevenlabs_provider`·`voice_import`에서 바꾸는 것은 `subprocess.run`의 키워드뿐. 예외 종류·메시지 틀·반환값 그대로 |
| 출력 형식 변경 | 만들어지는 wav/mp4/jpg의 바이트가 달라질 여지가 없다. `encoding`은 **우리가 읽는 방법**이지 자식이 **일하는 방법**이 아니다 |

### 자식의 환경은 건드리지 않는다

Sprint194에서 자식에게 `PYTHONIOENCODING=utf-8`을 주입했다가
되돌렸다. 그 지시는 **손자에게까지 상속되어** 남의 말을 로케일로 읽던
`test_script_resolver`를 대신 깨뜨렸다.

이번에도 `env=`는 쓰지 않는다. 고치는 것은 읽는 쪽뿐이다.

---

## 5. 제안하는 변경

각 호출식에 두 낱말을 더한다. 그 외에는 아무것도 손대지 않는다.

```python
     result = subprocess.run(
         command,
         capture_output=True,
         text=True,
+        encoding="utf-8",
+        errors="replace",
     )
```

### 왜 `utf-8`인가

측정했다(2절). ffmpeg·ffprobe는 UTF-8로 쓴다. 추측이 아니다.

### 왜 `errors="replace"`가 함께 필요한가

인코딩만 못 박으면 UTF-8이 아닌 바이트가 왔을 때 여전히 죽는다.
ffmpeg가 무엇을 흘릴지는 우리가 정하는 것이 아니다 — 코덱 이름,
메타데이터, 남이 만든 파일 안의 태그가 그대로 실려 나온다.

글자 몇 개가 `?`로 바뀌는 것과, 실패 이유를 통째로 잃는 것 중
무엇이 나은지는 분명하다.

### 왜 공용 함수로 빼지 않는가

`test_runner_service.decode_output()`은 한 스트림에 **인코딩이 둘 섞이는**
경우를 다룬다. 자식 unittest와 손자 ffmpeg가 각각 제 인코딩으로 쓰기
때문이었다. 여기는 자식이 ffmpeg 하나뿐이라 그 복잡함이 필요 없다.

새 import를 넣지 않는 편이 "최소 수정"에 맞다. 나중에 세 번째 자리가
생기면 그때 묶는다.

### 등급 B(8·9·10)도 함께 고칠 것인가

**고친다.** 셋만 남겨 두면 Sprint195에서 만든 원장(`LEFT_IN_APP`)을
계속 들고 다녀야 하고, "여기는 왜 예외인가"를 매번 설명해야 한다.
지금 무사한 이유가 **우리가 정한 규칙이 아니라 ffprobe 인자의
우연**이라는 점도 남겨 둘 이유가 못 된다.

다만 승인 시 등급 A(7곳)만 하는 선택도 가능하다. 그 경우 원장에
셋을 남기고 사유를 적는다.

---

## 6. 검증 계획

### 6.1 RED 먼저

Sprint195의 `tests/test_subprocess_encoding.py`가 이미 `app/`을 센다.
`LEFT_IN_APP`을 `{}`로 바꾸면 즉시 RED(10곳)가 된다. 새 스캐너를
만들지 않는다.

### 6.2 실측 테스트 — 진짜 ffmpeg로

AST 검사만으로는 부족하다. Sprint195에서 겪은 그대로다 — 검사 도구가
무엇을 못 보는지 모르면 통과가 곧 안전이 아니다.

`@unittest.skipUnless(ffmpeg 있음)` 아래에 실측을 둔다.

1. **한글 경로로 실패시킨다** — 없는 파일을 한글 폴더에서 찾게 한다
2. 올라온 예외의 메시지가 `None`이 아니고, 경로의 한글이 그대로
   실려 있는지 본다
3. 고치기 전에는 이 테스트가 실패해야 한다 (RED 확인)

ffmpeg가 없는 환경에서는 건너뛴다. 그 경우 AST 검사만 남는다는 것을
`skip` 사유에 적는다.

### 6.3 바뀌지 않았음을 확인한다

- 만들어진 파일의 바이트가 같은지 — 같은 입력으로 렌더해 해시 비교
- 예외의 **종류**가 같은지 (`Exception` / `VoiceImportError`)
- 성공 경로의 반환값이 같은지

### 6.4 전체 regression

`fail=0 error=0`. 기준선 4109 + 신규분.

`PYTHONUTF8` 같은 우회 없이 돌린다 — 우회를 쓰면 로케일이 UTF-8이
되어 이 결함 자체가 숨는다. Sprint192/193에서 두 번 그렇게 가려졌다.

---

## 7. 완료 조건

- [x] `app/` 10곳에 `encoding`·`errors` 명시 (+20줄, 명령 배열 불변)
- [x] `LEFT_IN_APP` = `{}`
- [x] 한글 경로 실패 실측 테스트가 RED → GREEN
      (RED 증상: `AssertionError: 'None' == 'None'`)
- [x] 산출물 바이트·예외 종류·반환값 불변 확인 (아래)
- [x] regression `ran=4112 failures=0 errors=0`, 우회 없이
- [x] 로컬 커밋까지. **Push 안 함**

### 불변 확인 실측 (수정 전 = `git stash`로 되돌린 HEAD)

| | 수정 전 | 수정 후 |
|---|---|---|
| `append_silence` sha256 | `31d85146b84fb8ba` | 같음 |
| `speed_up_audio` sha256 | `9ca58363e10b4ce0` | 같음 |
| 길이 (0.800 / 0.469 / 0.500) | | 같음 |
| 예외 종류 | `Exception` · `VoiceImportError` | 같음 |
| **실패 메시지** | **없음 (None)** | **있음** |

바뀐 것은 실패 이유가 살아 돌아온다는 것 하나뿐이다.

### 겪은 것 하나 — 시그니처를 고정한 mock

`test_asset_integration_service`의 side_effect가 production 호출을
위치 인자로 받고 있었다(`def _f(command, capture_output, text)`).
키워드가 늘자 TypeError가 났다. `**asked`로 바꿨다 - 그 테스트가 보는
것은 첫 프레임이 나오는가이지 무슨 키워드로 불렀는가가 아니다.

같은 유형을 전수 확인했다. 위치 인자로 받는 것은 저장소에서 그
하나뿐이고, 나머지는 `call_args[0][0]`으로 명령 배열만 읽으므로
키워드 추가와 무관하다.

---

## 8. 위험과 되돌리기

| 위험 | 판단 |
|---|---|
| 예외 메시지에 `?`가 섞일 수 있다 | 지금은 `None`이다. 나빠질 수 없다 |
| 로그 문자열이 길어져 성능에 영향 | 없음. 같은 양을 다른 코덱으로 읽을 뿐 |
| 렌더 결과가 달라진다 | 불가능. 자식에게 넘기는 인자가 그대로다 |
| 놓친 호출부가 있다 | 원장을 `{}`로 만들면 스캐너가 전수로 막는다 |

되돌리기는 커밋 하나를 `revert`하면 된다. 파일 간 의존이 없다.

---

## 9. 범위 밖 — 다음에 볼 것

- `print(result.stdout)` / `print(result.stderr)` (3곳). 렌더 로그를
  앱의 화면으로 그대로 쏟는다. 이것이 Sprint194에서 러너를 죽인
  "손자가 파이프에 UTF-8을 흘린다"의 정체일 가능성이 있다. 다만
  없애는 것은 **동작 변경**이라 이 스프린트에서 다루지 않는다.
- `duration_optimizer.get_audio_duration()`은 ffprobe가 실패해도
  `0.0`을 돌려준다. 인코딩과 무관한 별개 문제이고, 고치면 길이 판정이
  달라지므로 렌더 로직 변경에 해당한다.
