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
| GET | `/api/mobile/v1/dashboard` | Profile, active job, history summary, latest posture signals and trend when available |
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
Job and result responses include nullable `modelId` and `modelRelease` fields
so an analysis can be traced to the exact model plugin and immutable image tag.

The dashboard response uses these additional fields:

```json
{
  "prioritySignals": [],
  "latestSignals": [],
  "trend": null
}
```

`trend` is omitted (`null`) until at least eight comparable successful results
exist for one feature. The API never creates a score, range, confidence, or
coaching message from chart geometry. Missing model data remains missing in the
mobile response.

The result feature contract is populated from the model adapter. A model may
provide `feature_results.json` entries with `representative_value`,
`reference_range`, `series`, `verdict`, `confidence_pct`,
`confidence_level`, `interpretation`, `coaching_action`, `limitation`, and
`evidence_ids`. Legacy entries containing only `value` and `unit` remain
readable, but the app shows unavailable states for the fields that were not
provided.

For failed jobs, `stage` is mapped from the actual failed pipeline stage. For
example, a failure in `feature_extract` is shown as `자세 특성값 계산` rather
than being incorrectly reported as `결과 검증`.

## Local configuration

Set `EXPO_PUBLIC_API_BASE_URL` in `mobile/.env` before starting Expo:

```text
EXPO_PUBLIC_API_BASE_URL=https://<production-host>/api
```

For local or preview screen verification only, set
`EXPO_PUBLIC_DEMO_FIXTURES=true`. The app then uses clearly labelled
development fixtures for the home, progress, and result screens. Keep this
unset or `false` in production builds.

Run the reproducible checks from `mobile/`:

```bash
npm ci --legacy-peer-deps
npm run typecheck
npm run doctor
```

## Android internal distribution

`mobile/eas.json` defines the `preview` profile as EAS internal distribution
with Android `buildType: apk`. After linking this repository to an Expo project,
create an installable test build with:

```bash
cd mobile
npx eas-cli@latest login
npx eas-cli@latest init
npx eas-cli@latest build --platform android --profile preview
```

`eas init` adds the Expo account/project identifier and therefore requires the
project owner's Expo login. Do not commit signing credentials or access tokens.
