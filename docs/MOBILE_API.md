# Mobile API contract

`mobile/` is an Android-first Expo client for the existing API. The mobile
routes use JSON camelCase and a Bearer session; the web cookie routes remain
unchanged.

## Session and authentication

| Method | Endpoint | Purpose |
|---|---|---|
| POST | `/api/mobile/v1/sessions/guest` | Create a guest Bearer session |
| POST | `/api/mobile/v1/auth/kakao/start` | Create state and authorization URL |
| GET | `/api/mobile/v1/auth/kakao/callback` | Server-side Kakao callback |
| POST | `/api/mobile/v1/auth/kakao/exchange` | Consume one-time native exchange code |
| GET | `/api/mobile/v1/me` | Read current guest/account profile |
| PATCH | `/api/mobile/v1/me/profile` | Save `heightCm` |
| POST | `/api/mobile/v1/auth/logout` | Revoke current session |
| DELETE | `/api/mobile/v1/me/data` | Delete current user's data |

The native redirect is `runnersfeed://auth/callback`. The server-side Kakao
redirect is HTTPS and must be registered separately in Kakao Developers:

```text
https://<production-host>/api/mobile/v1/auth/kakao/callback
```

The app does not contain `API_KEY`. Production Nginx injects the internal
`X-API-Key` before forwarding the request to the API.

## Analysis lifecycle

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/api/mobile/v1/dashboard` | Profile, active job, history summary |
| POST | `/api/mobile/v1/uploads` | Get signed PUT URL for MP4/MOV |
| POST | `/api/mobile/v1/uploads/complete` | Validate uploaded object |
| POST | `/api/mobile/v1/jobs` | Start analysis with `inputObjectName` and `userHeightCm` |
| GET | `/api/mobile/v1/jobs` | List owned jobs |
| GET | `/api/mobile/v1/jobs/{jobId}` | Poll status and stage |
| GET | `/api/mobile/v1/jobs/{jobId}/result` | Read validated report contract |
| POST | `/api/mobile/v1/jobs/{jobId}/result-video-url` | Get expiring result video URL |

The mobile result contract renders only fields returned by the report adapter.
If a feature has no reference range, series, confidence, or evidence, the app
shows an explicit unavailable state instead of deriving one from the chart.

## Local configuration

Set `EXPO_PUBLIC_API_BASE_URL` in `mobile/.env` before starting Expo:

```text
EXPO_PUBLIC_API_BASE_URL=https://<production-host>/api
```

Run the reproducible checks from `mobile/`:

```bash
npm ci --legacy-peer-deps
npm run typecheck
npm run doctor
```
