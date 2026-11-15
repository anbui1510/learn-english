# Mobile via Capacitor (US-G3-030)

Wraps the existing Vite/React learner web UI in a native Android/iOS shell.
No React Native rewrite — karaoke, shadowing, and mic recording reuse the web code.

## Prerequisites

- Node 20+/22+
- Android Studio (Android) or Xcode (iOS, macOS only)
- API reachable from the device/emulator (`VITE_API_BASE_URL`)

## Build & run Android

```bash
cd frontend
npm ci
# Point the WebView at your API (LAN IP for a physical phone)
echo 'VITE_API_BASE_URL=http://10.0.2.2:8000' > .env.local   # emulator → host loopback
npm run cap:android
```

Then Run ▶ in Android Studio.

## iOS (macOS)

The `frontend/ios/` Xcode project is committed. Build/run still needs macOS + Xcode:

```bash
cd frontend
npm run cap:ios
```

OAuth URL scheme `com.learnenglish.app` and mic usage string are in `ios/App/App/Info.plist`.

## Backend CORS / cookies

Capacitor WebViews use origins such as `https://localhost` (Android) and
`capacitor://localhost` (iOS). The API allows these via `FRONTEND_ORIGINS`
(see `backend/.env.example`).

For production mobile auth against HTTPS APIs, set:

```
COOKIE_SECURE=true
COOKIE_SAMESITE=none
FRONTEND_ORIGIN=https://your.app.domain
FRONTEND_ORIGINS=https://localhost,capacitor://localhost,...
```

### OAuth return into the shell

Native sign-in opens Google in a Custom Tab (`@capacitor/browser`) with
`return_to=com.learnenglish.app://auth/callback`. After Google callback, the API
redirects to that deep link with a **one-time** `code` (never the JWT). The app
exchanges it via `POST /auth/exchange` and receives the `le_session` cookie.

Allowlist via `MOBILE_AUTH_RETURN_URIS` (defaults include `https://localhost/` and
`com.learnenglish.app://auth/callback`). Unlisted `return_to` values fall back to
`FRONTEND_ORIGIN`.

For production mobile auth against HTTPS APIs, also set `COOKIE_SECURE=true` and
`COOKIE_SAMESITE=none` so the WebView can store the session cookie cross-origin.

## Mic permission

Android `RECORD_AUDIO` is declared in `android/app/src/main/AndroidManifest.xml`.
iOS uses `NSMicrophoneUsageDescription` in Info.plist.
The learner role-play button requests `getUserMedia` and surfaces a denial message
when permission is blocked.

## Offline karaoke cache

Opening a dialogue online stores lesson JSON (IndexedDB, last 3) and line audio
(Cache API). Offline, `fetchLesson` / `fetchShadowing` fall back to cache and the
UI shows an offline banner. Scoring, uploads, and new downloads still need network.

## Sync after web changes

```bash
cd frontend
npm run cap:sync
```
