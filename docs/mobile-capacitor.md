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

```bash
cd frontend
npx cap add ios   # once
npm run cap:ios
```

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

Google OAuth still redirects to the configured web `FRONTEND_ORIGIN` after login;
deep-link return into the shell is a follow-up if store distribution needs it.

## Mic permission

Android `RECORD_AUDIO` is declared in `android/app/src/main/AndroidManifest.xml`.
The learner role-play button requests `getUserMedia` and surfaces a denial message
when permission is blocked.

## Sync after web changes

```bash
cd frontend
npm run cap:sync
```
