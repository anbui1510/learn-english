import { useCallback, useEffect, useState } from 'react'
import {
  getCase,
  listCaseFacts,
  listMyCases,
  startExtract,
  type CaseDraft,
  type ClinicalFact,
} from './api'

type Props = {
  onError: (message: string | null) => void
}

async function waitForExtract(caseId: number): Promise<CaseDraft> {
  for (let attempt = 0; attempt < 40; attempt += 1) {
    const draft = await getCase(caseId)
    if (
      draft.extract_status === 'succeeded' ||
      draft.extract_status === 'failed'
    ) {
      return draft
    }
    await new Promise((resolve) => setTimeout(resolve, 250))
  }
  return getCase(caseId)
}

export function EditorFacts({ onError }: Props) {
  const [cases, setCases] = useState<CaseDraft[]>([])
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [facts, setFacts] = useState<ClinicalFact[]>([])
  const [statusFilter, setStatusFilter] = useState('needs_review')
  const [busy, setBusy] = useState(false)
  const [extractNote, setExtractNote] = useState<string | null>(null)

  const refreshCases = useCallback(async () => {
    const listed = await listMyCases()
    setCases(listed)
    if (selectedId == null && listed.length > 0) {
      setSelectedId(listed[0].id)
    }
  }, [selectedId])

  const refreshFacts = useCallback(
    async (caseId: number) => {
      const listed = await listCaseFacts(caseId, {
        status: statusFilter || undefined,
      })
      setFacts(listed)
    },
    [statusFilter],
  )

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const listed = await listMyCases()
        if (cancelled) return
        setCases(listed)
        if (listed.length > 0) {
          setSelectedId((prev) => prev ?? listed[0].id)
        }
      } catch (err) {
        if (!cancelled) {
          onError(err instanceof Error ? err.message : 'Failed to load cases')
        }
      }
    })()
    return () => {
      cancelled = true
    }
  }, [onError])

  useEffect(() => {
    if (selectedId == null) {
      setFacts([])
      return
    }
    let cancelled = false
    ;(async () => {
      try {
        const listed = await listCaseFacts(selectedId, {
          status: statusFilter || undefined,
        })
        if (!cancelled) setFacts(listed)
      } catch (err) {
        if (!cancelled) {
          onError(err instanceof Error ? err.message : 'Failed to load facts')
        }
      }
    })()
    return () => {
      cancelled = true
    }
  }, [selectedId, statusFilter, onError])

  const selected = cases.find((c) => c.id === selectedId) ?? null

  async function onExtract() {
    if (selectedId == null) return
    setBusy(true)
    onError(null)
    setExtractNote(null)
    try {
      await startExtract(selectedId)
      const draft = await waitForExtract(selectedId)
      await refreshCases()
      if (draft.extract_status === 'failed') {
        setExtractNote(draft.extract_error ?? 'Extraction failed')
      } else {
        setExtractNote(`Extract ${draft.extract_status}`)
        await refreshFacts(selectedId)
      }
    } catch (err) {
      onError(err instanceof Error ? err.message : 'Extract failed')
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="mt-8 border-t border-slate-200 pt-8">
      <h2 className="text-xl font-semibold tracking-tight">Extract facts</h2>
      <p className="mt-1 text-sm text-slate-600">
        Run extraction on an uploaded case, then browse quote-backed fact cards.
      </p>

      {cases.length === 0 ? (
        <p className="mt-4 text-sm text-slate-500">
          Upload a PDF case first to enable extraction.
        </p>
      ) : (
        <div className="mt-4 flex flex-col gap-3">
          <label className="text-sm">
            Case
            <select
              className="mt-1 w-full rounded border border-slate-300 px-2 py-1"
              value={selectedId ?? ''}
              onChange={(e) => setSelectedId(Number(e.target.value))}
            >
              {cases.map((c) => (
                <option key={c.id} value={c.id}>
                  #{c.id} — {c.title} ({c.extract_status})
                </option>
              ))}
            </select>
          </label>

          {selected ? (
            <p className="text-sm text-slate-500">
              Status: {selected.extract_status}
              {selected.extract_error ? ` — ${selected.extract_error}` : ''}
            </p>
          ) : null}

          <button
            type="button"
            disabled={busy || selectedId == null || !selected?.pdf_object_key}
            onClick={() => void onExtract()}
            className="w-fit rounded-md bg-teal-700 px-3 py-2 text-sm font-medium text-white hover:bg-teal-600 disabled:opacity-60"
          >
            {busy ? 'Extracting…' : 'Start extract'}
          </button>

          {extractNote ? (
            <p className="text-sm text-slate-600">{extractNote}</p>
          ) : null}

          <label className="text-sm">
            Filter status
            <select
              className="mt-1 w-full rounded border border-slate-300 px-2 py-1"
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
            >
              <option value="needs_review">needs_review</option>
              <option value="verified">verified</option>
              <option value="">all</option>
            </select>
          </label>

          <ul className="mt-2 flex flex-col gap-3">
            {facts.map((fact) => (
              <li
                key={fact.id}
                className="border-l-2 border-teal-600 pl-3 text-sm text-slate-800"
              >
                <p className="font-medium">{fact.atomic_fact}</p>
                <p className="mt-1 text-slate-600">
                  “{fact.source_quote}”
                </p>
                <p className="mt-1 text-xs text-slate-500">
                  {fact.category} · p.{fact.page} · {fact.status}
                </p>
              </li>
            ))}
            {facts.length === 0 ? (
              <li className="text-sm text-slate-500">No facts for this filter.</li>
            ) : null}
          </ul>
        </div>
      )}
    </section>
  )
}
