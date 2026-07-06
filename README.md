# wellbeingplant-ai
WellbeingPlant AI Factory

## 환경변수

`cloud-run/.env.example`을 `cloud-run/.env`로 복사한 뒤 값을 채우세요.
`cloud-run/app/__init__.py`가 앱 시작 시 자동으로 `.env`를 로드합니다
(파일이 없으면 조용히 건너뛰고, 이미 설정된 실제 환경변수는 덮어쓰지
않습니다 - Cloud Run 배포 환경에서는 `.env` 없이 서비스 환경변수만
설정하면 됩니다).

| 변수 | 필수 여부 | 설명 |
|---|---|---|
| `TTS_PROVIDER` | 선택 (기본 `google`) | `google` 또는 `elevenlabs` |
| `ELEVENLABS_API_KEY` | `TTS_PROVIDER=elevenlabs`일 때 필수 | ElevenLabs API Key |
| `ELEVENLABS_VOICE_ID` | 선택 | ElevenLabs Voice ID (`_VOICE_NAME` 없을 때 사용) |
| `ELEVENLABS_VOICE_NAME` | 선택 | ElevenLabs Voice 이름 (설정 시 우선 사용) |
| `PEXELS_API_KEY` | 선택 | 미설정/검색 실패 시 AI Image로 자동 폴백 |
| `PIXABAY_API_KEY` | 선택 | 미설정/검색 실패 시 AI Image로 자동 폴백 |
| `GOOGLE_APPLICATION_CREDENTIALS` | Gemini/Imagen/Google TTS 사용 시 필요 | Google SDK가 ADC로 직접 읽음(앱 코드가 읽지 않음) |
| `ASSET_MODE` | 선택 (기본 `balanced`) | `low_cost`/`balanced`/`premium` - Hybrid Asset Engine의 AI 사용 상한 및 Pexels 품질 기준 (Sprint38) |

자세한 예시는 `cloud-run/.env.example` 참고.
