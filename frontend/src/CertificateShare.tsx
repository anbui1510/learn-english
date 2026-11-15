import { useEffect, useState } from 'react'
import { fetchSharedCertificate, type SharedCertificate } from './api'

type Props = {
  shareSlug: string
  onClose: () => void
}

export function CertificateShare({ shareSlug, onClose }: Props) {
  const [cert, setCert] = useState<SharedCertificate | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const data = await fetchSharedCertificate(shareSlug)
        if (!cancelled) setCert(data)
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Could not load certificate')
        }
      }
    })()
    return () => {
      cancelled = true
    }
  }, [shareSlug])

  return (
    <section className="mt-6 border-t border-slate-200 pt-6">
      <div className="flex items-start justify-between gap-3">
        <h2 className="text-xl font-semibold tracking-tight">
          Practice certificate
        </h2>
        <button
          type="button"
          className="text-sm text-slate-500 underline"
          onClick={onClose}
        >
          Close
        </button>
      </div>
      {error ? (
        <p className="mt-3 text-sm text-red-700" role="alert">
          {error}
        </p>
      ) : null}
      {!cert && !error ? (
        <p className="mt-3 text-sm text-slate-500">Loading…</p>
      ) : null}
      {cert ? (
        <div className="mt-4 space-y-2 text-sm text-slate-700">
          <p className="text-lg font-medium text-slate-900">{cert.title}</p>
          <p>
            Module <span className="font-medium">{cert.module_slug}</span>
            {' · '}
            {cert.cme_points} virtual CME
            {' · '}
            rank {cert.rank_at_issue}
          </p>
          <p className="text-xs text-slate-500">{cert.disclaimer}</p>
          <p className="text-xs text-slate-400">Issued {cert.created_at}</p>
        </div>
      ) : null}
    </section>
  )
}
