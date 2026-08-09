# Sprint197 SPEC — Render 로그 출력 구조 안정화

- 상태: 완료 (승인 · A안 · 검증 통과)
- 선행: Sprint194 `684e187`, Sprint195 `674fca6`, Sprint196 `894c23e`
- 기준선: regression `ran=4112 failures=0 errors=0`
- 결과: regression `ran=4121 failures=0 errors=0`

7절은 **A**로 승인됐다. 이번엔 print만 처리하고, 예외 메시지에 남는
경로는 측정해서 숫자로 남긴다(9절).

---

## 1. 목표

렌더가 실패했을 때 이유가 사라지지 않고, 성공했을 때 화면이 ffmpeg
배너로 덮이지 않게 한다.

Sprint194~196이 **읽는 것**을 고쳤다면(자식의 말을 못 읽어 `None`이
되던 문제), 이번은 **읽은 뒤 그것을 어디에 쏟는가**다.

---

## 2. 그 print는 화면으로 간다

이것이 이 스프린트의 전제다. 확인한 경로다.

```
audio_service.concat_scene_audio   print(result.stdout) / print(result.stderr)
audio_service.mix_audio            print(result.stdout) / print(result.stderr)
final_video_service.merge_video_audio  print(result.stdout) / print(result.stderr)
        |
        v  studio_jobs._Tee 가 sys.stdout 을 가로챈다
job["console"]  (상한 400줄, 넘으면 앞에서부터 버린다)
        |
        v  GET /studio/api/jobs/{id}?console_from=N
studio.html  <div class="console">
```

`_Tee`는 원래 stdout으로도 흘리면서 작업 버퍼에 쌓는다. 즉 이 세
자리의 출력은 **사용자가 보는 Console 패널의 내용**이다.

### 실측 — 얼마나 쏟는가

```
scene 오디오 잇기 (concat 계열)     26줄   그중 절대 경로 2줄
최종 mp4 (merge 계열)              55줄   그중 절대 경로 3줄
실패: 없는 입력                     14줄   그중 절대 경로 1줄
```

세 자리는 렌더 한 번에 각각 한 번씩 불린다. 합쳐서 **약 116줄**,
Console 상한 400줄의 **약 29%**다. 파이프라인이 남기는 진짜 진행
메시지가 그만큼 밀려난다.

### 실측 — 무엇이 실려 나가는가

```
Input #0, concat, from 'C:\Users\baeku\AppData\Local\Temp\...\list.txt':
Error opening input file C:\Users\baeku\AppData\Local\Temp\...\없다.wav.
```

사용자 이름이 든 절대 경로다. 이 저장소는 이미 이것을 문제로 보고
있다 — `beta_render_events.crashed()`에 이렇게 적혀 있다.

> 예외로 끝났다. **종류만 적는다 - 메시지에는 경로가 들어 있다.**

베타 기록에는 종류만 남기면서, 정작 화면에는 경로가 그대로 찍힌다.

---

## 3. 지금 무엇이 사라지는가

**실패 이유는 사라지지 않는다.** print를 지워도 남는다. 경로가 둘이기
때문이다.

```
raise Exception(result.stderr)
        |
        v  studio_jobs._run 의 except
_append_line(job_id, f"[Studio] 생성 실패: {exc}")   -> Console
job["error"] = str(exc)                              -> API -> 화면
```

즉 **print는 실패 보존에 기여하지 않는다.** 같은 내용을 예외가 이미
나르고 있고, print는 그것을 한 번 더, 그것도 성공했을 때까지 찍는다.

사라지는 쪽은 오히려 반대다. 렌더가 이 세 자리를 지나며 116줄을
쏟으면, 그 앞에 있던 파이프라인 메시지가 400줄 상한에서 밀려 나간다.
**로그가 사라지는 원인이 이 print 자신이다.**

---

## 4. 범위

| 파일 | 함수 | print |
|---|---|---|
| `app/services/audio_service.py` | `concat_scene_audio` | stdout·stderr |
| `app/services/audio_service.py` | `mix_audio` | stdout·stderr |
| `app/services/final_video_service.py` | `merge_video_audio` | stdout·stderr |

관련 테스트: `test_audio_service`, `test_audio_policy`,
`test_final_video_service`.

---

## 5. 지워도 되는 근거

**아무도 이 출력을 읽지 않는다.** 확인한 것 셋이다.

1. 진행 단계는 로그로 판정하지 않는다. `studio_jobs` 첫머리에 그
   원칙이 적혀 있다 — "로그 문구에 기대면 파이프라인이 print를 바꿀
   때마다 UI가 조용히 틀린다." 판정은 디스크의 산출물이 한다.
2. Console에서 뜻을 갖는 줄은 `Project :` 하나뿐이고, 그것은
   `factory_service`가 찍는다. ffmpeg 출력이 아니다.
3. ffmpeg 출력을 단언하는 테스트가 없다. `builtins.print`를 가로채는
   테스트는 `asset_selector`·`release`·`voice_resolver` 쪽이고 이
   세 자리와 무관하다.

---

## 6. 제안

### 6.1 권고안 — `logger.debug`로 옮긴다

```python
-    print(result.stdout)
-    print(result.stderr)
+    logger.debug("ffmpeg stdout: %s", result.stdout)
+    logger.debug("ffmpeg stderr: %s", result.stderr)
```

- 기본 설정에서 `debug`는 아무 데도 나가지 않는다. Console이 조용해진다
- `logging`은 `sys.stdout`을 쓰지 않으므로 `_Tee`에 잡히지 않는다.
  화면과 로그가 분리된다
- 필요하면 레벨을 올려 되살릴 수 있다. **지우는 것과 달리 되돌릴 수
  있다**
- 저장소에 선례가 있다 — `atomic_write`, `s3_compatible_storage_provider`

### 6.2 대안 — 그냥 지운다

더 작다. 다만 "필요하면 볼 수 있다"를 잃는다. 렌더가 이상할 때
ffmpeg가 뭐라고 했는지 다시 보려면 코드를 고쳐야 한다.

**6.1을 권한다.** 허용 범위의 "안전한 logging 처리"에 해당하고,
없애는 것보다 되돌리기 쉽다.

---

## 7. 결정이 필요한 것 — 예외 메시지의 경로

print를 없애도 **경로 노출은 남는다.**

```python
raise Exception(result.stderr)     # 배너 + 경로가 통째로 예외 메시지
        -> job["error"] -> 화면
```

실패했을 때 사용자 화면에 `C:\Users\baeku\...`가 그대로 뜬다. 세
가지 중 하나를 골라야 한다.

| | 내용 | 비용 |
|---|---|---|
| **A. 손대지 않는다** | 이번엔 print만. 경로 노출은 다음에 | 승인 범위 그대로 · 문제는 남음 |
| **B. 뒷부분만 남긴다** | ffmpeg의 진짜 오류는 끝에 있다. 배너를 빼고 마지막 N줄만 예외에 담는다 | 예외 **메시지**가 바뀐다. 종류는 유지 |
| **C. 경로를 가린다** | 홈 경로를 `~`로 치환 | 가장 안전 · 변경이 가장 큼 |

**A를 권한다.** 이번 스프린트의 허용 목록은 print 처리이고, B·C는
"사용자에게 필요한 오류 메시지 유지"와 맞닿아 있어 따로 논의하는
편이 낫다. 다만 이 스프린트에서 **측정만 해 두고**(검증 3항),
남은 노출을 숫자로 보고한다.

승인 시 B나 C를 지시하면 그에 맞춰 계획을 고친다.

---

## 8. 검증 계획

### 8.1 RED 먼저

새 파일 `tests/test_render_log_output.py`.

1. **성공 렌더가 화면을 더럽히지 않는다** — `subprocess.run`을 가로채
   ffmpeg 배너를 흉내 낸 stderr를 돌려주고, `builtins.print`가 그것을
   찍지 않는지 본다. 지금은 실패한다
2. **절대 경로가 화면으로 안 간다** — 배너에 홈 경로를 심어 두고,
   찍힌 것에 그 경로가 없는지 본다. 지금은 실패한다

### 8.2 실패 출력이 사라지지 않는지 (GREEN 유지)

3. **실패 이유는 예외에 그대로 남는다** — `returncode != 0`일 때
   올라온 예외 메시지에 ffmpeg가 말한 오류 줄이 있는지 본다.
   지금도 통과해야 하고, 고친 뒤에도 통과해야 한다
4. **예외 종류가 같다** — `Exception`(세 자리 모두)

### 8.3 개인정보 노출 측정

5. 실패 예외 메시지에 남는 절대 경로 줄 수를 세어 보고한다.
   이 스프린트에서 고치지 않기로 한 것(7절 A)을 **숫자로 남긴다**

### 8.4 성공 렌더 결과 동일

6. Sprint196과 같은 방법 — `git stash`로 수정 전 코드를 되살려
   같은 입력으로 만들고 **sha256을 비교**한다. 대상은 세 함수가
   만드는 산출물(이어붙인 음성, 믹스, 최종 mp4)

### 8.5 전체 regression

`fail=0 error=0`. 기준선 4112 + 신규분. `PYTHONUTF8` 우회 없이.

---

## 9. 완료 조건

- [x] 세 자리 6줄을 `logger.debug`로 옮김 (6.1 권고안)
- [x] 실패 원인이 예외에 남음 (테스트로 고정)
- [x] 예외 종류 불변 (`Exception`)
- [x] 성공 렌더 산출물 sha256 불변
- [x] Console에 ffmpeg 배너·절대 경로가 안 감 (테스트로 고정)
- [x] 남은 경로 노출 측정치 보고 (아래)
- [x] regression `ran=4121 failures=0 errors=0`
- [x] 로컬 커밋까지. **Push 안 함**

### 실측 (수정 전 = `git stash`로 되돌린 HEAD)

| | 수정 전 | 수정 후 |
|---|---|---|
| `concat_scene_audio` sha256 | `648e5f87e64b0d78` | 같음 |
| `merge_video_audio` sha256 | `973ed50d463f16c4` | 같음 |
| **Console에 쌓인 줄** | **26줄** | **0줄** |
| **그중 절대 경로** | **2줄** | **0줄** |
| 예외 종류 · 이유 보존 | `Exception` · 있음 | 같음 |
| 예외 메시지 안 절대 경로 | 2줄 | **2줄 (그대로)** |

### 남은 노출 — 다음 범위

실패했을 때 `job["error"]`로 화면에 가는 예외 메시지에는 **절대 경로
2줄**이 그대로 남아 있다. 7절에서 A를 고른 결과이고, 고치려면 B(뒷부분만)
또는 C(경로 마스킹)를 따로 승인해야 한다.

화면에 상시로 찍히던 것(성공·실패 모두, 렌더마다 26~55줄)과, 실패했을
때만 예외에 실려 가는 것은 노출 빈도가 다르다. 큰 쪽을 먼저 없앴다.

---

## 10. 위험과 되돌리기

| 위험 | 판단 |
|---|---|
| 렌더 결과가 달라진다 | 불가능. ffmpeg에 넘기는 인자를 건드리지 않는다 |
| 디버깅이 어려워진다 | `logger.debug`라 레벨만 올리면 돌아온다. 지우는 안(6.2)보다 이 점이 낫다 |
| Console이 너무 조용해진다 | 파이프라인 자신의 진행 메시지는 그대로다. 없어지는 것은 ffmpeg 배너뿐이고, 오히려 그 메시지가 밀려나지 않는다 |
| 로그를 읽던 무언가가 깨진다 | 5절에서 확인했다 - 읽는 곳이 없다 |

되돌리기는 커밋 하나를 `revert`하면 된다.

---

## 11. 범위 밖

- `_Tee`와 `MAX_CONSOLE_LINES`는 건드리지 않는다. 쏟는 쪽을 줄이는
  것이 먼저다
- 파이프라인의 다른 `print`들. 그것은 이 앱이 진행을 알리는 방식이고,
  이번 대상은 **남의 프로그램 출력을 그대로 옮기는** 세 자리다
- 예외 메시지의 경로 마스킹 (7절 B·C). 지시가 있으면 포함한다
