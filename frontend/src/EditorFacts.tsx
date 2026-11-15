import { useCallback, useEffect, useState } from 'react'
import {
  generateDialogues,
  getCase,
  listCaseFacts,
  listMyCases,
  patchCaseFact,
  publishCase,
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
  const [note, setNote] = useState<string | null>(null)

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
    setNote(null)
    try {
      await startExtract(selectedId)
      const draft = await waitForExtract(selectedId)
      await refreshCases()
      if (draft.extract_status === 'failed') {
        setNote(draft.extract_error ?? 'Extraction failed')
      } else {
        setNote(`Extract ${draft.extract_status}`)
        await refreshFacts(selectedId)
      }
    } catch (err) {
      onError(err instanceof Error ? err.message : 'Extract failed')
    } finally {
      setBusy(false)
    }
  }

  async function onSetStatus(
    fact: ClinicalFact,
    status: ClinicalFact['status'],
  ) {
    if (selectedId == null) return
    setBusy(true)
    onError(null)
    try {
      await patchCaseFact(selectedId, fact.id, { status })
      await refreshFacts(selectedId)
      await refreshCases()
    } catch (err) {
      onError(err instanceof Error ? err.message : 'Fact update failed')
    } finally {
      setBusy(false)
    }
  }

  async function onPublish() {
    if (selectedId == null) return
    setBusy(true)
    onError(null)
    setNote(null)
    try {
      const draft = await publishCase(selectedId)
      setNote(`Case #${draft.id} published`)
      await refreshCases()
    } catch (err) {
      onError(err instanceof Error ? err.message : 'Publish failed')
    } finally {
      setBusy(false)
    }
  }

  async function onGenerate() {
    if (selectedId == null) return
    setBusy(true)
    onError(null)
    setNote(null)
    try {
      const result = await generateDialogues(selectedId)
      if ('ok' in result) {
        setNote('Dialogues generated')
      } else if (result.status === 409) {
        setNote('Publish the case before generate-dialogues (409).')
      } else if (result.status === 501) {
        setNote('Dialogue generation reserved for epic 5 (501).')
      } else {
        onError(`generate-dialogues failed (${result.status})`)
      }
    } catch (err) {
      onError(err instanceof Error ? err.message : 'generate-dialogues failed')
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="mt-8 border-t border-slate-200 pt-8">
      <h2 className="text-xl font-semibold tracking-tight">
        Extract & review facts
      </h2>
      <p className="mt-1 text-sm text-slate-600">
        Extract, verify or reject fact cards, then publish the case.
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
                  #{c.id} — {c.title} ({c.status}/{c.extract_status})
                </option>
              ))}
            </select>
          </label>

          {selected ? (
            <p className="text-sm text-slate-500">
              Extract: {selected.extract_status}
              {selected.extract_error ? ` — ${selected.extract_error}` : ''}
              {selected.status === 'published' && selected.published_at
                ? ` · published ${selected.published_at}`
                : ''}
            </p>
          ) : null}

          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              disabled={busy || selectedId == null || !selected?.pdf_object_key}
              onClick={() => void onExtract()}
              className="rounded-md bg-teal-700 px-3 py-2 text-sm font-medium text-white hover:bg-teal-600 disabled:opacity-60"
            >
              {busy ? 'Working…' : 'Start extract'}
            </button>
            <button
              type="button"
              disabled={busy || selectedId == null || selected?.status === 'published'}
              onClick={() => void onPublish()}
              className="rounded-md bg-slate-900 px-3 py-2 text-sm font-medium text-white hover:bg-slate-800 disabled:opacity-60"
            >
              Publish case
            </button>
            <button
              type="button"
              disabled={busy || selectedId == null}
              onClick={() => void onGenerate()}
              className="rounded-md border border-slate-300 px-3 py-2 text-sm font-medium text-slate-800 hover:bg-slate-100 disabled:opacity-60"
            >
              Generate dialogues
            </button>
          </div>

          {note ? <p className="text-sm text-slate-600">{note}</p> : null}

          <label className="text-sm">
            Filter status
            <select
              className="mt-1 w-full rounded border border-slate-300 px-2 py-1"
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
            >
              <option value="needs_review">needs_review</option>
              <option value="verified">verified</option>
              <option value="rejected">rejected</option>
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
                <div className="mt-2 flex flex-wrap gap-2">
                  <button
                    type="button"
                    disabled={busy || fact.status === 'verified'}
                    onClick={() => void onSetStatus(fact, 'verified')}
                    className="text-xs font-medium text-teal-800 underline disabled:opacity-40"
                  >
                    Verify
                  </button>
                  <button
                    type="button"
                    disabled={busy || fact.status === 'rejected'}
                    onClick={() => void onSetStatus(fact, 'rejected')}
                    className="text-xs font-medium text-slate-700 underline disabled:opacity-40"
                  >
                    Reject
                  </button>
                </div>
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
