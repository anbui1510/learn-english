import { useEffect, useState } from 'react'

/** Lightweight online/offline indicator for cached karaoke replay. */
export function OfflineBanner() {
  const [offline, setOffline] = useState(
    () => typeof navigator !== 'undefined' && !navigator.onLine,
  )

  useEffect(() => {
    const on = () => setOffline(false)
    const off = () => setOffline(true)
    window.addEventListener('online', on)
    window.addEventListener('offline', off)
    return () => {
      window.removeEventListener('online', on)
      window.removeEventListener('offline', off)
    }
  }, [])

  if (!offline) return null

  return (
    <p
      className="rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-950"
      role="status"
    >
      Offline — replaying cached lessons only. Scoring, uploads, and new downloads
      need a connection.
    </p>
  )
}
