# ADOPTION-04 — Identity audit: WellbeingPlant

Audit only. **No source changed, no dependency added, no authentication
built.**

## Which project

"WellbeingPlant" names two different codebases, so both were audited:

| | What it is |
|---|---|
| `C:\Projects\wellbeingplant-ai` | *WellbeingPlant AI Factory* — a FastAPI service on Cloud Run that produces and publishes video. 484 Python files. |
| `C:\Projects\ai-bridge\apps\wellbeing` | the Flutter health assistant. 431 Dart files. |

**Neither owns identity.** The conclusion is the same for both, for
different reasons.

## Finding 1 — the AI Factory (`wellbeingplant-ai`)

The keyword sweep returns large numbers, and every one of them is the
app authenticating **itself to somebody else's platform**, never a user
authenticating to this app.

| Term | Files | What it actually is |
|---|---|---|
| authentication | 14 | `google_oauth_service.py`, `instagram_oauth_service.py`, `oauth_health.py`, and LLM/voice **provider** API-key auth |
| login / logout / refresh | 20 / 4 / 32 | `_OAUTH_ACTIONS = ("login", "refresh", "logout")` — OAuth against YouTube and Instagram |
| account | 35 | `account_id` — the **YouTube/Instagram channel** being published to |
| credential / token | 44 / 54 | OAuth credentials and access tokens for those platforms |
| permission | 14 | YouTube/Meta API error codes — `insufficientPermissions`, `_PERMISSION_ERROR_CODES` |
| password | 2 | a comment saying the credential model has **no** password field, and a test asserting it never gains one |
| jwt, organization, tenant, license, subscription | 0 | — |

There is **no user table, no ORM user model, no session store**, and no
authentication on any route: `main.py` and the routers declare no
`Depends`, no `HTTPBearer`, no middleware.

Publishing to YouTube is the app acting as a *client* of Google. The
Identity Platform manages *your* users; it does not hold your YouTube
channel tokens, and pointing it at them would be a category error.

## Finding 2 — the health app (`ai-bridge/apps/wellbeing`)

Zero for authentication, login, logout, signup, jwt, password, bcrypt,
credential, role, organization, tenant, license, subscription.

The four large counts are all something else:

| Term | Count | What it actually is |
|---|---|---|
| user | 147 files | **prose in doc comments** — "a user who logs water at 23:50", "what the user measured". Only 4 capitalised `User`, all in sentences ("User-facing copy"). No entity, no model. |
| token | 83 files | **`AppTokens`** — Flutter design tokens. 1,378 occurrences of "tokens", 150 of `AppTokens`. |
| permission | 36 files | **`HealthPermissionState`**, `HealthPermissionDenied`, `health_permission.dart` — the *operating system* granting access to health data. |
| session | 18 files | an exercise/walk **session**, and conversation state. |

The app makes **no network calls at all** — no `http`, no `dio`, no API
client. It is offline, storing to local SQLite via drift. An app with no
backend cannot have a backend session.

## Classification

| Class | Meaning | What fell here |
|---|---|---|
| **A** — real identity responsibility | user account, authentication, authorization, session, password | **nothing, in either project** |
| **B** — business/domain concept | | exercise sessions, conversation state, health-data records |
| **C** — technical, unrelated | | OAuth to YouTube/Instagram, provider API keys, `AppTokens` design tokens, OS health permissions, "account for" as an English verb, widget registration, UI refresh |

Nothing was classified A, so nothing is a migration target.

## Migration decision

**Audit only.** Section 3 of the mission is explicit: if no identity
ownership exists, no source changes and no dependency changes. The
Identity SDK was not added, because Section 4 permits adding it only
when a migration target exists.

## Contract safety (Section 5)

Both projects would be *broken*, not improved, by adding authentication:

* **AI Factory.** Its API is consumed by static pages it serves itself —
  `studio.html`, `queue.html`, `replay.html`. They have no login flow and
  no way to hold a token. Putting authentication in front of the routers
  would leave the studio UI unable to call its own backend.
* **Health app.** It has no network layer whatsoever. Authentication
  would mean introducing a backend dependency into an app that
  deliberately works offline, which would break its core promise rather
  than secure anything.

Neither has an existing consumer that authenticates, so there is nothing
to preserve and nothing to gain.

## The principle this confirms

Established by ADOPTION-03 and unchanged here:

> **Identity Platform adoption means replacing existing identity
> ownership — not adding authentication to consumers that do not own it.**

AI ERP and AI Bridge each had a real implementation to hand over.
AI Order Hub had none. WellbeingPlant has none either, in either of the
two codebases that carry the name.

## One observation, recorded not acted on

The AI Factory is deployed to Cloud Run and serves an API with **no
authentication of any kind**. Whether that is correct depends on how the
service is exposed — Cloud Run can require IAM at the platform edge, in
which case the application needs none. That is a deployment question,
not an identity-ownership question, and answering it was outside this
audit. Noted so it is not mistaken for something this audit cleared.
