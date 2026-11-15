import { useCallback, useEffect, useState } from 'react'
import {
  generateDialogues,
  getCase,
  listCaseDialogues,
  listCaseFacts,
  listMyCases,
  patchCaseFact,
  patchCaseProgression,
  publishCase,
  startExtract,
  synthesizeDialogue,
  type CaseDraft,
  type CefrLevel,
  type ClinicalFact,
  type DialogueArtifact,
  type DialogueContext,
} from './api'

type Props = {
  onError: (message: string | null) => void
}

const ALL_CONTEXTS: DialogueContext[] = [
  'patient_family',
  'colleague_sbar',
  'expert_cme',
]

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
  const [dialogues, setDialogues] = useState<DialogueArtifact[]>([])
  const [statusFilter, setStatusFilter] = useState('needs_review')
  const [contexts, setContexts] = useState<DialogueContext[]>([
    'patient_family',
  ])
  const [cefrLevel, setCefrLevel] = useState<CefrLevel>('B1')
  const [includeVi, setIncludeVi] = useState(false)
  const [busy, setBusy] = useState(false)
  const [note, setNote] = useState<string | null>(null)
  const [moduleSlug, setModuleSlug] = useState('')
  const [unlockCme, setUnlockCme] = useState(0)
  const [unlockRank, setUnlockRank] = useState('')
  const [unlockRequiresCaseId, setUnlockRequiresCaseId] = useState('')

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

  const refreshDialogues = useCallback(async (caseId: number) => {
    const listed = await listCaseDialogues(caseId)
    setDialogues(listed)
  }, [])

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
      setDialogues([])
      return
    }
    let cancelled = false
    ;(async () => {
      try {
        const [factList, dialogueList] = await Promise.all([
          listCaseFacts(selectedId, { status: statusFilter || undefined }),
          listCaseDialogues(selectedId),
        ])
        if (!cancelled) {
          setFacts(factList)
          setDialogues(dialogueList)
        }
      } catch (err) {
        if (!cancelled) {
          onError(err instanceof Error ? err.message : 'Failed to load case data')
        }
      }
    })()
    return () => {
      cancelled = true
    }
  }, [selectedId, statusFilter, onError])

  const selected = cases.find((c) => c.id === selectedId) ?? null

  useEffect(() => {
    if (!selected) return
    setModuleSlug(selected.module_slug ?? '')
    setUnlockCme(selected.unlock_cme_points ?? 0)
    setUnlockRank(selected.unlock_rank ?? '')
    setUnlockRequiresCaseId(
      selected.unlock_requires_case_id != null
        ? String(selected.unlock_requires_case_id)
        : '',
    )
  }, [selected])

  function toggleContext(context: DialogueContext) {
    setContexts((prev) =>
      prev.includes(context)
        ? prev.filter((c) => c !== context)
        : [...prev, context],
    )
  }

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

  async function onSaveProgression() {
    if (selectedId == null) return
    setBusy(true)
    onError(null)
    try {
      const reqId = unlockRequiresCaseId.trim()
      await patchCaseProgression(selectedId, {
        module_slug: moduleSlug.trim() || null,
        unlock_cme_points: unlockCme,
        unlock_rank: unlockRank || null,
        unlock_requires_case_id: reqId ? Number(reqId) : null,
        clear_unlock_requires_case: !reqId,
      })
      await refreshCases()
      setNote('Progression rules saved')
    } catch (err) {
      onError(err instanceof Error ? err.message : 'Progression update failed')
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
    if (selectedId == null || contexts.length === 0) return
    setBusy(true)
    onError(null)
    setNote(null)
    try {
      const created = await generateDialogues(selectedId, {
        contexts,
        cefr_level: cefrLevel,
        include_vi: includeVi,
      })
      for (const dialogue of created) {
        await synthesizeDialogue(selectedId, dialogue.id)
      }
      const warned = created.filter((d) => d.duration_warning).length
      setNote(
        warned > 0
          ? `Generated + synthesized ${created.length} dialogue(s); ${warned} exceed ~2 min.`
          : `Generated + synthesized ${created.length} dialogue(s).`,
      )
      await refreshDialogues(selectedId)
    } catch (err) {
      onError(err instanceof Error ? err.message : 'generate-dialogues failed')
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="mt-8 border-t border-slate-200 pt-8">
      <h2 className="text-xl font-semibold tracking-tight">
        Extract, review & dialogues
      </h2>
      <p className="mt-1 text-sm text-slate-600">
        Extract facts, verify them, publish the case, then generate CEFR dialogues.
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
            <>
            <p className="text-sm text-slate-500">
              Extract: {selected.extract_status}
              {selected.extract_error ? ` — ${selected.extract_error}` : ''}
              {selected.status === 'published' && selected.published_at
                ? ` · published ${selected.published_at}`
                : ''}
            </p>
            <div className="grid gap-2 rounded border border-slate-200 p-3 text-sm sm:grid-cols-2">
              <label>
                Module slug
                <input
                  className="mt-1 w-full rounded border border-slate-300 px-2 py-1"
                  value={moduleSlug}
                  onChange={(e) => setModuleSlug(e.target.value)}
                  placeholder="peds-respiratory"
                />
              </label>
              <label>
                Unlock CME points
                <input
                  type="number"
                  min={0}
                  className="mt-1 w-full rounded border border-slate-300 px-2 py-1"
                  value={unlockCme}
                  onChange={(e) => setUnlockCme(Number(e.target.value))}
                />
              </label>
              <label>
                Unlock rank
                <select
                  className="mt-1 w-full rounded border border-slate-300 px-2 py-1"
                  value={unlockRank}
                  onChange={(e) => setUnlockRank(e.target.value)}
                >
                  <option value="">None</option>
                  <option value="intern">Intern</option>
                  <option value="resident">Resident</option>
                  <option value="fellow">Fellow</option>
                  <option value="attending">Attending</option>
                  <option value="chief_of_staff">Chief of Staff</option>
                </select>
              </label>
              <label>
                Requires case id
                <input
                  className="mt-1 w-full rounded border border-slate-300 px-2 py-1"
                  value={unlockRequiresCaseId}
                  onChange={(e) => setUnlockRequiresCaseId(e.target.value)}
                  placeholder="optional"
                />
              </label>
              <button
                type="button"
                disabled={busy}
                onClick={() => void onSaveProgression()}
                className="sm:col-span-2 w-fit rounded-md border border-slate-300 px-3 py-1.5 disabled:opacity-50"
              >
                Save unlock rules
              </button>
            </div>
            </>
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
          </div>

          <fieldset className="mt-2 border-t border-slate-200 pt-3">
            <legend className="text-sm font-medium text-slate-800">
              Generate dialogues
            </legend>
            <div className="mt-2 flex flex-col gap-2 text-sm">
              {ALL_CONTEXTS.map((context) => (
                <label key={context} className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    checked={contexts.includes(context)}
                    onChange={() => toggleContext(context)}
                  />
                  {context}
                </label>
              ))}
              <label>
                CEFR
                <select
                  className="mt-1 w-full rounded border border-slate-300 px-2 py-1"
                  value={cefrLevel}
                  onChange={(e) => setCefrLevel(e.target.value as CefrLevel)}
                >
                  <option value="A2">A2</option>
                  <option value="B1">B1</option>
                  <option value="C1">C1</option>
                </select>
              </label>
              <label className="flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={includeVi}
                  onChange={(e) => setIncludeVi(e.target.checked)}
                />
                Include Vietnamese gloss
              </label>
              <button
                type="button"
                disabled={
                  busy ||
                  selectedId == null ||
                  selected?.status !== 'published' ||
                  contexts.length === 0
                }
                onClick={() => void onGenerate()}
                className="w-fit rounded-md border border-slate-300 px-3 py-2 text-sm font-medium text-slate-800 hover:bg-slate-100 disabled:opacity-60"
              >
                Generate dialogues
              </button>
            </div>
          </fieldset>

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

          <div className="mt-4 border-t border-slate-200 pt-4">
            <h3 className="text-base font-semibold">Dialogues</h3>
            <ul className="mt-2 flex flex-col gap-4">
              {dialogues.map((dialogue) => (
                <li key={dialogue.id} className="text-sm text-slate-800">
                  <p className="font-medium">
                    #{dialogue.id} · {dialogue.context} · {dialogue.cefr_level} ·{' '}
                    ~{dialogue.estimated_seconds}s
                    {dialogue.duration_warning ? ' · over 2 min' : ''}
                  </p>
                  <ol className="mt-2 list-decimal space-y-1 pl-5 text-slate-700">
                    {dialogue.lines.map((line, index) => (
                      <li key={`${dialogue.id}-${index}`}>
                        <span className="font-medium">{line.speaker}:</span>{' '}
                        {line.text}
                        <span className="block text-xs text-slate-500">
                          facts: {line.fact_ids.join(', ')}
                          {line.text_vi ? ` · ${line.text_vi}` : ''}
                        </span>
                      </li>
                    ))}
                  </ol>
                </li>
              ))}
              {dialogues.length === 0 ? (
                <li className="text-sm text-slate-500">No dialogues yet.</li>
              ) : null}
            </ul>
          </div>
        </div>
      )}
    </section>
  )
}
