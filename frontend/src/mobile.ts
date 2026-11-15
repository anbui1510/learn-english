import { Capacitor } from '@capacitor/core'

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
