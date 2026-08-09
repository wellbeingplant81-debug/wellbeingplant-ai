# ADOPTION-07 — Identity audit: AI Video Studio

Audit only. **No source changed, no dependency added, no authentication
built.**

## First: this is the same codebase as ADOPTION-04

`cloud-run/app/app_info.py` declares `NAME = "AI영상제작소"` — AI Video
Studio. The repository directory is `wellbeingplant-ai` and the README
calls it *WellbeingPlant AI Factory*.

So the project audited here under the name **AI Video Studio** is the
same code audited three batches ago under the name **WellbeingPlant**
(`docs/adoption-04-identity-audit.md`, commit `4ce643d`). One codebase,
three names. Recorded plainly because a future reader given one of those
names should not go looking for a second project that does not exist.

This audit is therefore a **re-verification at current HEAD** plus the
surfaces ADOPTION-07 names that ADOPTION-04 did not specifically
inspect: worker processes, the render pipeline, queue processing, batch
generation, CLI tools and database models.

## Re-verification

The keyword sweep at current HEAD returns **counts identical to
ADOPTION-04**, including across the Sprint 185 and 186 commits landed
since. The identity surface has not moved.

`signup`, `jwt`, `bcrypt`, `organization`, `tenant`, `license`,
`subscription`: still 0.

## The surfaces ADOPTION-07 adds

### Workers, queue and batch

Three modules: `routers/batch.py`, `services/studio_jobs.py`,
`tests/test_production_queue_workflow.py`.

**A job has no owner.** `studio_jobs.py` declares no `owner`, no
`user_id`, no `created_by`, no `requested_by`. `generate_batch` takes a
`BatchRequest` and nothing else — no `Depends`, no principal, no caller
identity of any kind. Work in this system is anonymous by construction.

### Database models

There are none. No SQLAlchemy, no SQLModel, no Firestore, no sqlite3.
State is JSON written to a GCS bucket. There is no table in which a user
could be stored, and none that carries a foreign key to one.

### CLI tools

None. The only `click` in the codebase is the word "click-through" in
`thumbnail_service.py`. There is no command-line entry point to
authenticate.

### Render and publishing pipeline

`publishing_plan_model.py` carries `scheduled_at` and `schedule_state`,
driven by `PublishingController.schedule_plan()`. Publishing runs on a
schedule, unattended. Nothing in that path reads a caller identity.

## Section 4 — the external platform boundary

Every large count is the application authenticating **itself to somebody
else's platform**. None is a person authenticating to this application.

| What | Where | Class |
|---|---|---|
| Google/YouTube OAuth | `google_oauth_service.py`, `file_token_store.py`, `oauth_credential.py` | **B** |
| Instagram OAuth | `instagram_oauth_service.py`, `instagram_credential.py`, `instagram_token_store.py` | **B** |
| `account_id` (35 files) | the **channel** being published to | **B** |
| LLM / voice provider API keys | `stage_provider.py`, `current_engine.py`, `local_voice.py` | **B** |
| `permission` (14) | YouTube/Meta API error codes — `insufficientPermissions`, `_PERMISSION_ERROR_CODES` | **B** |
| `login` / `logout` / `refresh` | `_OAUTH_ACTIONS` against those platforms | **B** |
| `password` (2) | a comment saying the credential model has **no** password field, and a test asserting it never gains one | **B** |
| `hash` (31) | content and asset hashing | **D** |
| `token` (54) | OAuth access tokens (B) and LLM token counts (D) | **B/D** |

The separation the mission asks for is already explicit in the code. An
`OAuthCredential` is *for a channel*, keyed by `account_id`; it is not a
person's account with this software. Nothing in the system asks "who are
you" — only "which channel am I posting to".

## Section 5 — pipeline safety

**The project already enforces the rule this section states**, for its
own OAuth, and the reasoning is written down in `routers/studio.py`:

    상태 조회만 동기다(로컬 토큰 파일만 읽으므로 즉시 끝난다).
    ...
    login만 브라우저를 연다. 사용자가 버튼을 눌렀을 때만 이 경로가
    호출되며, 상태 조회(GET)는 절대 여기로 오지 않는다.

`GET /api/oauth/status` reads the stored token file and **never touches
the network**, precisely so that opening a screen cannot cause a browser
to launch by itself. Only `login` is interactive, and only on a button
press.

That is the same principle Section 5 asks me to protect — and adding
application authentication would break it:

* **Scheduled rendering / publishing** — `scheduled_at` fires without
  anybody present. An interactive login would stall the schedule.
* **Background workers and queue processing** — the OAuth actions
  already run as background tasks because login "can block for hundreds
  of seconds waiting on a browser redirect". Putting a second, unrelated
  login in front of the queue would compound exactly that problem.
* **Batch generation** — `generate_batch` is a single anonymous call;
  a principal requirement would change its contract.
* **The studio UI** — `studio.html`, `queue.html` and `replay.html` are
  static pages this service serves itself. They have no login flow and
  nowhere to hold a token, so authentication in front of the routers
  would leave the studio unable to call its own backend.

## Classification

| Class | What fell here |
|---|---|
| **A** — real identity responsibility | **nothing** |
| **B** — external service ownership | Google/YouTube OAuth, Instagram OAuth, `account_id` channels, LLM and voice API keys, external permission error codes |
| **C** — video domain data | channel metadata, publishing plans, schedule state |
| **D** — technical, unrelated | LLM token counts, content hashes, background-task state |

Nothing is Class A.

## Migration decision

**Audit only.** Section 3 requires no source and no dependency changes
when only B/C/D exist; Section 4 permits the SDK only when a target
exists. Neither condition is met, and the finding is unchanged from
ADOPTION-04.

## Carried forward, still not acted on

The service is deployed to Cloud Run and serves its API with **no
authentication of any kind** — no `Depends`, no `HTTPBearer`, no
middleware. Whether that is correct depends on whether IAM is enforced
at the platform edge, which is a deployment question rather than an
identity-ownership one. ADOPTION-04 recorded it; it remains open, and
this audit did not clear it.

## The principle, unchanged

> **Identity Platform adoption means replacing existing identity
> ownership — not adding authentication to consumers that do not own it.**
