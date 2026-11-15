import type { CapacitorConfig } from '@capacitor/cli'

const config: CapacitorConfig = {
  appId: 'com.learnenglish.app',
  appName: 'LearnEnglish',
  webDir: 'dist',
  server: {
    // Dev tip: set CAPACITOR_SERVER_URL to hit Vite while iterating on-device.
    // androidScheme keeps cookie-friendly https origin in the WebView.
    androidScheme: 'https',
  },
  plugins: {
    SplashScreen: {
      launchShowDuration: 1200,
      backgroundColor: '#0f172a',
    },
  },
}

export default config
