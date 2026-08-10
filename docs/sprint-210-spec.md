# Sprint210 SPEC — 경로는 글자가 아니라 자리로 본다

- 상태: 완료 (구현 · 검증 통과)
- 선행: Sprint209 `3ad589f`
- 기준선: regression `ran=4262 failures=0 errors=0`
- 결과: regression `ran=4268 failures=0 errors=0` · 서비스 하나
  (+36/-2)

## 고친 뒤 다시 잰 결과

Sprint209에서 거짓 경보가 났던 그 배치를 그대로 재현했다.

| 경우 | 실제로 안에 있는가 | 전 | 후 |
|---|---|---|---|
| 이웃, 이름 겹침 | 아니오 | **X** | **O** |
| 이웃, 이름 다름 | 아니오 | O | O |
| 진짜 안쪽 | 예 | X | X |

세 경우가 실제 사실과 정확히 일치한다.

RED에서 **이웃 케이스 하나만** 실패했고 나머지 다섯은 처음부터
통과했다 - 고칠 것만 고쳤다는 뜻이다.

---

## 1. 무엇이 틀렸는가

`beta_package_validation._user()`가 경로를 **글자로** 비교한다.

```python
"separated": not home.startswith(program)
```

경로는 글자가 아니라 자리다. `C:\Temp\RC209-home`은 `C:\Temp\RC209`로
시작하지만 그 **안에 있지 않다** - 이름이 겹치는 이웃일 뿐이다.

Sprint209에서 절차를 밟다가 드러났다.

```
프로그램  C:\Temp\AI영상제작소-RC209
내 자리   C:\Temp\AI영상제작소-RC209-home

실제로 안에 있는가   아니오
판정                 X  (거짓 경보)
```

### 어느 쪽으로 틀렸는가

| 경우 | 실제 | 지금 판정 | 옳은 판정 |
|---|---|---|---|
| 이웃이고 이름이 겹침 | 밖 | **X** | **O** |
| 이웃이고 이름이 다름 | 밖 | O | O |
| 진짜로 안쪽 | 안 | X | X |
| 같은 폴더 | 안 | X | X |

**안전한데 위험하다고 말한다.** 반대(위험한데 안전하다)는 없다. 그래서
급하지는 않지만, 거짓 경보는 사람이 검사를 믿지 않게 만든다.

---

## 2. 뜻은 그대로 둔다

이 줄이 묻는 것은 바뀌지 않는다.

> 내 것이 프로그램 폴더 **밖에** 있는가

바꾸는 것은 **"안에 있다"를 어떻게 재는가**뿐이다. O/X/? 기준도,
줄 이름도, 설명도 그대로다.

---

## 3. 어떻게 고치는가

```python
def _inside(child: str, parent: str) -> bool:
    """child가 parent 안에 있는가. 글자가 아니라 자리로 본다."""

    try:
        return os.path.commonpath([child, parent]) == parent
    except ValueError:
        # 드라이브가 다르면 겹칠 수 없다. commonpath가 그때 던진다.
        return False
```

`commonpath`는 조각 단위로 본다. `C:\Temp\RC209-home`과
`C:\Temp\RC209`의 공통 자리는 `C:\Temp`이고 그것은 `C:\Temp\RC209`가
아니므로 **밖**이다.

`startswith`로 같은 일을 하려면 구분자를 손으로 붙여야 하고
(`parent + os.sep`), 그러면 드라이브 뿌리(`C:\`)에서 어긋난다.
파이썬이 이미 아는 일을 우리가 다시 짜지 않는다.

### 두 줄 다 같은 자로 잰다

`separated`(프로그램 자리 기준)와 `no_write`(받은 폴더 기준)가 같은
질문을 다른 기준점으로 묻는다. 둘 다 `_inside`를 쓴다.

---

## 4. 이번 범위 밖 — 그러나 같은 결함

`beta_readiness.py`에 **글자 그대로 같은 비교**가 있다.

```python
# app/services/beta_readiness.py
separated = not os.path.normcase(os.path.abspath(home)).startswith(
    os.path.normcase(os.path.abspath(program)))
```

이번 지시의 범위는 `beta_package_validation.py`이므로 고치지 않는다.

**그래서 이웃 폴더에서는 두 자리가 다른 말을 하게 된다.** 지금
`test_the_separation_matches_readiness`가 둘이 같은지 보고 있는데, 그
테스트는 이름이 겹치지 않는 임시 폴더를 쓰므로 계속 통과한다 - 즉
**이 어긋남을 아무도 잡지 못한다.**

고치려면 같은 `_inside`를 쓰면 된다. 별도 승인 사항으로 남긴다.

---

## 5. 검증

### RED

1. 이웃인데 이름이 겹치면 `separated`가 X다 (지금)
2. 같은 경우 `no_write`도 X다 (지금)

### GREEN

3. 이웃이고 이름이 겹쳐도 O
4. 이웃이고 이름이 다르면 O (그대로)
5. 진짜로 안쪽이면 X (그대로)
6. 같은 폴더면 X (그대로)
7. 드라이브가 달라도 죽지 않고 O

### 건드리지 않았음

8. 줄 이름·설명·O/X/? 기준 그대로
9. 셈(passed/failed/unknown)이 같은 자리에서 나온다
10. 절대 경로가 답에 없다
11. 만들지 않는다 (두 번 불러도 디스크 그대로)

---

## 6. 완료 조건

- [ ] `_inside` 하나로 두 줄을 잰다
- [ ] 이웃·안쪽·같은 폴더·다른 드라이브 넷 다 확인
- [ ] 뜻·이름·기준 불변
- [ ] `beta_readiness`의 같은 결함을 보고
- [ ] regression `fail=0 error=0`
- [ ] 로컬 커밋. **Push 안 함**
