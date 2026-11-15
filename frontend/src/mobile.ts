import { Capacitor } from '@capacitor/core'
import {
  createPkcePair,
  exchangeAuthCode,
  loginUrl,
  MOBILE_AUTH_RETURN_URI,
  storePkceVerifier,
  takePkceVerifier,
} from './api'

/** True when running inside a Capacitor native shell (not plain browser). */
export function isNativePlatform(): boolean {
  return Capacitor.isNativePlatform()
}

export function nativePlatformName(): string {
  return Capacitor.getPlatform()
}

/**
 * Request mic access early so Android/iOS prompt before role-play recording.
 * Falls back to a no-op on web when Permissions API is unavailable.
 */
export async function ensureMicrophonePermission(): Promise<boolean> {
  if (!navigator.mediaDevices?.getUserMedia) {
    return false
  }
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
    stream.getTracks().forEach((track) => track.stop())
    return true
  } catch {
    return false
  }
}

export async function bootstrapNativeShell(): Promise<void> {
  if (!isNativePlatform()) return
  try {
    const { StatusBar, Style } = await import('@capacitor/status-bar')
    await StatusBar.setStyle({ style: Style.Dark })
  } catch {
    // Plugin optional on web preview.
  }
  try {
    const { SplashScreen } = await import('@capacitor/splash-screen')
    await SplashScreen.hide()
  } catch {
    // ignore
  }
}

/**
 * Open Google OAuth in a Custom Tab / SFSafariViewController, returning via
 * deep link `com.learnenglish.app://auth/callback?code=…` (code only; PKCE
 * verifier stays in sessionStorage).
 */
export async function startNativeGoogleLogin(): Promise<void> {
  const { verifier, challenge } = await createPkcePair()
  storePkceVerifier(verifier)
  const url = loginUrl(MOBILE_AUTH_RETURN_URI, challenge)
  if (!isNativePlatform()) {
    window.location.assign(url)
    return
  }
  const { Browser } = await import('@capacitor/browser')
  await Browser.open({ url, presentationStyle: 'popover' })
}

/** Accept only the exact OAuth callback deep link (blocks open-redirect style URLs). */
export function isTrustedAuthCallback(url: string): boolean {
  try {
    const parsed = new URL(url)
    const protocol = parsed.protocol.replace(/:$/, '')
    if (protocol !== 'com.learnenglish.app') return false
    if (parsed.hostname !== 'auth') return false
    if (parsed.pathname !== '/callback') return false
    return true
  } catch {
    return /^com\.learnenglish\.app:\/\/auth\/callback(?:\?|#|$)/.test(url)
  }
}

function codeFromDeepLink(url: string): string | null {
  if (!isTrustedAuthCallback(url)) return null
  try {
    const parsed = new URL(url)
    return parsed.searchParams.get('code')
  } catch {
    const match = /[?&]code=([^&]+)/.exec(url)
    return match ? decodeURIComponent(match[1]) : null
  }
}

/**
 * Listen for OAuth deep-link return; exchange one-time code + PKCE verifier
 * for session cookie. Call once at app start; invoke `onSession` after success.
 */
export async function listenForAuthDeepLink(
  onSession: () => void | Promise<void>,
): Promise<() => void> {
  if (!isNativePlatform()) {
    return () => undefined
  }
  const { App } = await import('@capacitor/app')
  const { Browser } = await import('@capacitor/browser')

  const handle = async (url: string) => {
    if (!isTrustedAuthCallback(url)) return
    const code = codeFromDeepLink(url)
    if (!code) return
    const verifier = takePkceVerifier()
    if (!verifier) {
      throw new Error('Missing PKCE verifier for auth exchange')
    }
    try {
      await Browser.close()
    } catch {
      // Browser may already be closed.
    }
    await exchangeAuthCode(code, verifier)
    await onSession()
  }

  const listener = await App.addListener('appUrlOpen', (event) => {
    void handle(event.url).catch((err) => {
      console.error('Auth deep link failed', err)
    })
  })

  // Cold start: app opened from the deep link itself.
  try {
    const launch = await App.getLaunchUrl()
    if (launch?.url) {
      void handle(launch.url).catch((err) => {
        console.error('Auth launch URL failed', err)
      })
    }
  } catch {
    // getLaunchUrl unavailable on some platforms.
  }

  return () => {
    void listener.remove()
  }
}
