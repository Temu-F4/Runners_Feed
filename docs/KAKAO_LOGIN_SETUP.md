# Kakao Login setup

The application implements Kakao authorization-code login at these endpoints:

- Start: `/api/auth/kakao/start`
- Callback: `/api/auth/kakao/callback`
- Current account: `/api/me`
- Local logout: `/api/auth/logout`

Kakao access and refresh tokens are not stored. The database stores the Kakao
user identifier and, when the user has granted access, email and nickname.

## Kakao Developers configuration

1. Create or select the application in Kakao Developers.
2. Add the production HTTPS origin under **Platform > Web**.
3. Enable **Kakao Login**.
4. Register this exact redirect URI:

   ```text
   https://<PRODUCTION_HOST>/api/auth/kakao/callback
   ```

5. Configure the nickname and email consent items required by the service.
   Login still works when Kakao does not return either optional field.
6. Copy the REST API key. If Client Secret is enabled, copy that value as well.

Do not commit either value to Git.

## Production environment

Add these values to the protected production environment file used by the
deployment runner:

```dotenv
KAKAO_REST_API_KEY=<REST_API_KEY>
KAKAO_CLIENT_SECRET=<CLIENT_SECRET_OR_EMPTY>
KAKAO_REDIRECT_URI=https://<PRODUCTION_HOST>/api/auth/kakao/callback
ACCOUNT_SESSION_TTL_DAYS=30
```

The redirect URI must match Kakao Developers exactly, including scheme, host,
path, and absence of a trailing slash. Restarting or deploying the API makes the
new environment available.

## Identity behavior

- Visitors can continue without logging in.
- First login converts the current guest user into an account, preserving jobs.
- Logging into an existing Kakao account from a new browser moves that browser's
  guest jobs to the existing account.
- Account sessions use a random, hashed server-side token in a Secure, HttpOnly,
  SameSite=Lax cookie and expire after 30 days by default.
- Logout removes the current local session. It does not disconnect the service
  from the user's Kakao account.
- Deleting user data removes jobs, stored artifacts, OAuth identity, and account
  sessions through the existing `/api/me/data` flow.
