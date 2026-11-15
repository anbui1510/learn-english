import { useEffect, useMemo, useRef, useState } from 'react'
import {
  completeLesson,
  completeSrsCard,
  fetchLearnerProfile,
  fetchLesson,
  fetchProgression,
  fetchShadowing,
  fetchSkillTree,
  fetchSrsQueue,
  fetchWordReplay,
  listLearnerCaseDialogues,
  listPublishedCases,
  patchLearnerProfile,
  uploadAttemptAudio,
  type AttemptScore,
  type CefrLevel,
  type EmpathyScore,
  type Lesson,
  type Progression,
  type PublishedCase,
  type ShadowingCard,
  type SkillTreeNode,
  type SrsCard,
} from './api'

type Props = {
  onError: (message: string | null) => void
}

type CaseDialogue = {
  id: number
  context: string
  cefr_level: string
}

export function LearnerPanel({ onError }: Props) {
  const [cases, setCases] = useState<PublishedCase[]>([])
  const [caseId, setCaseId] = useState<number | null>(null)
  const [dialogueId, setDialogueId] = useState<number | null>(null)
  const [dialogues, setDialogues] = useState<CaseDialogue[]>([])
  const [lesson, setLesson] = useState<Lesson | null>(null)
  const [cards, setCards] = useState<ShadowingCard[]>([])
  const [lineIndex, setLineIndex] = useState(0)
  const [speed, setSpeed] = useState(1)
  const [showVi, setShowVi] = useState(false)
  const [activeWord, setActiveWord] = useState(-1)
  const [lessonsPerWeek, setLessonsPerWeek] = useState(3)
  const [cefrPackage, setCefrPackage] = useState<CefrLevel>('B1')
  const [note, setNote] = useState<string | null>(null)
  const [cardIndex, setCardIndex] = useState(0)
  const [recording, setRecording] = useState(false)
  const [uploadingAttempt, setUploadingAttempt] = useState(false)
  const [lastScore, setLastScore] = useState<AttemptScore | null>(null)
  const [lastEmpathy, setLastEmpathy] = useState<EmpathyScore | null>(null)
  const [responseMode, setResponseMode] = useState<'read_along' | 'free_speech'>(
    'read_along',
  )
  const [srsCards, setSrsCards] = useState<SrsCard[]>([])
  const [progression, setProgression] = useState<Progression | null>(null)
  const [skillTree, setSkillTree] = useState<SkillTreeNode[]>([])
  const replayAudioRef = useRef<HTMLAudioElement | null>(null)
  const audioRef = useRef<HTMLAudioElement | null>(null)
  const mediaRecorderRef = useRef<MediaRecorder | null>(null)
  const mediaChunksRef = useRef<Blob[]>([])
  const mediaStreamRef = useRef<MediaStream | null>(null)

  const current = lesson?.playlist[lineIndex] ?? null
  const speakerColor = useMemo(() => {
    if (!current) return 'text-teal-800'
    return current.speaker.toLowerCase().includes('parent') ||
      current.speaker.toLowerCase().includes('nurse')
      ? 'text-orange-700'
      : 'text-teal-800'
  }, [current])

  async function refreshSrs() {
    const queue = await fetchSrsQueue(1)
    setSrsCards(queue)
  }

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const [listed, profile, queue, prog, tree] = await Promise.all([
          listPublishedCases(),
          fetchLearnerProfile(),
          fetchSrsQueue(1),
          fetchProgression(),
          fetchSkillTree(),
        ])
        if (cancelled) return
        setCases(listed)
        setLessonsPerWeek(profile.lessons_per_week)
        setCefrPackage(profile.cefr_package)
        setSrsCards(queue)
        setProgression(prog)
        setSkillTree(tree)
        const firstOpen = listed.find((c) => c.unlocked !== false)
        if (firstOpen) setCaseId(firstOpen.id)
      } catch (err) {
        if (!cancelled) {
          onError(
            err instanceof Error ? err.message : 'Failed to load learner data',
          )
        }
      }
    })()
    return () => {
      cancelled = true
    }
  }, [onError])

  useEffect(() => {
    if (caseId == null) return
    let cancelled = false
    ;(async () => {
      try {
        const listed = await listLearnerCaseDialogues(caseId)
        if (cancelled) return
        setDialogues(listed)
        setDialogueId(listed[0]?.id ?? null)
      } catch (err) {
        if (!cancelled) {
          onError(
            err instanceof Error ? err.message : 'Failed to list dialogues',
          )
        }
      }
    })()
    return () => {
      cancelled = true
    }
  }, [caseId, onError])

  useEffect(() => {
    if (dialogueId == null) {
      setLesson(null)
      setCards([])
      return
    }
    let cancelled = false
    ;(async () => {
      try {
        const [lessonBody, shadowCards] = await Promise.all([
          fetchLesson(dialogueId),
          fetchShadowing(dialogueId),
        ])
        if (cancelled) return
        setLesson(lessonBody)
        setCards(shadowCards)
        setLineIndex(0)
        setCardIndex(0)
        setActiveWord(-1)
      } catch (err) {
        if (!cancelled) {
          onError(err instanceof Error ? err.message : 'Failed to load lesson')
        }
      }
    })()
    return () => {
      cancelled = true
    }
  }, [dialogueId, onError])

  useEffect(() => {
    const audio = audioRef.current
    if (!audio || !current) return
    audio.pause()
    audio.src = current.audio_url
    audio.playbackRate = speed
    setActiveWord(-1)
  }, [current, speed])

  useEffect(() => {
    const audio = audioRef.current
    if (!audio || !current) return
    const onTime = () => {
      const ms = audio.currentTime * 1000 * speed
      // playbackRate already stretches time; use currentTime*1000 for media position
      const mediaMs = audio.currentTime * 1000
      const idx = current.timestamps.findIndex(
        (stamp) =>
          mediaMs >= stamp.offset_ms &&
          mediaMs < stamp.offset_ms + stamp.duration_ms,
      )
      setActiveWord(idx)
      void ms
    }
    audio.addEventListener('timeupdate', onTime)
    return () => audio.removeEventListener('timeupdate', onTime)
  }, [current, speed])

  async function onSaveProfile() {
    onError(null)
    try {
      const profile = await patchLearnerProfile({
        lessons_per_week: lessonsPerWeek,
        cefr_package: cefrPackage,
      })
      setNote(
        `Saved journey: ${profile.lessons_per_week}/week · ${profile.cefr_package} · ${profile.path_months} months`,
      )
    } catch (err) {
      onError(err instanceof Error ? err.message : 'Failed to save profile')
    }
  }

  async function onReplayRedWord(word: string) {
    if (dialogueId == null) return
    onError(null)
    try {
      const snippet = await fetchWordReplay({
        dialogueId,
        lineIndex,
        word,
      })
      const audio = replayAudioRef.current ?? new Audio()
      replayAudioRef.current = audio
      audio.pause()
      audio.src = snippet.audio_url
      const startSec = snippet.start_ms / 1000
      const endSec = snippet.end_ms / 1000
      const onTime = () => {
        if (audio.currentTime >= endSec) {
          audio.pause()
          audio.removeEventListener('timeupdate', onTime)
        }
      }
      audio.addEventListener('timeupdate', onTime)
      audio.currentTime = startSec
      await audio.play()
      setNote(`Replaying AI sample: “${snippet.word}”`)
    } catch (err) {
      onError(err instanceof Error ? err.message : 'Replay failed')
    }
  }

  async function onComplete() {
    if (dialogueId == null) return
    onError(null)
    try {
      const result = await completeLesson(dialogueId)
      const prog = await fetchProgression()
      setProgression(prog)
      const listed = await listPublishedCases()
      setCases(listed)
      const bits = [`+${result.cme_awarded} CME`]
      if (result.rank_label) bits.push(result.rank_label)
      if (result.certificate?.share_slug) {
        bits.push(`cert ${result.certificate.share_slug}`)
      }
      setNote(`Lesson complete · ${bits.join(' · ')}`)
    } catch (err) {
      onError(err instanceof Error ? err.message : 'Failed to complete')
    }
  }

  function stopMediaTracks() {
    mediaStreamRef.current?.getTracks().forEach((track) => track.stop())
    mediaStreamRef.current = null
  }

  async function onToggleMicRecord() {
    if (dialogueId == null) return
    onError(null)

    if (recording) {
      mediaRecorderRef.current?.stop()
      return
    }

    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === 'undefined') {
      onError('Microphone recording is not supported in this browser')
      return
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      mediaStreamRef.current = stream
      mediaChunksRef.current = []
      const mimeType = MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
        ? 'audio/webm;codecs=opus'
        : MediaRecorder.isTypeSupported('audio/webm')
          ? 'audio/webm'
          : ''
      const recorder = mimeType
        ? new MediaRecorder(stream, { mimeType })
        : new MediaRecorder(stream)
      mediaRecorderRef.current = recorder
      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) mediaChunksRef.current.push(event.data)
      }
      recorder.onerror = () => {
        setRecording(false)
        stopMediaTracks()
        onError('Microphone recording failed')
      }
      recorder.onstop = () => {
        setRecording(false)
        stopMediaTracks()
        const blob = new Blob(mediaChunksRef.current, {
          type: recorder.mimeType || 'audio/webm',
        })
        mediaChunksRef.current = []
        void (async () => {
          if (blob.size === 0) {
            onError('No audio captured — try again')
            return
          }
          setUploadingAttempt(true)
          try {
            const result = await uploadAttemptAudio({
              dialogueId,
              mode: 'role_play',
              file: blob,
              lineIndex,
              score: true,
              responseMode,
            })
            setLastScore(result.score ?? null)
            setLastEmpathy(result.empathy ?? null)
            await refreshSrs()
            const pa = result.score
            const srsNote =
              (result.srs_enqueued ?? 0) > 0
                ? ` · ${result.srs_enqueued} SRS card(s) queued for T+1`
                : ''
            setNote(
              pa
                ? `PA ${pa.engine}: pronunciation ${pa.pronunciation} · completeness ${pa.completeness} · prosody ${pa.prosody}${srsNote}`
                : 'Attempt audio saved without score',
            )
          } catch (err) {
            onError(err instanceof Error ? err.message : 'Upload failed')
          } finally {
            setUploadingAttempt(false)
          }
        })()
      }
      recorder.start()
      setRecording(true)
      setNote('Recording… tap Stop when finished')
    } catch {
      stopMediaTracks()
      onError('Microphone permission denied or unavailable')
    }
  }

  return (
    <section className="mt-8 border-t border-slate-200 pt-8">
      <h2 className="text-xl font-semibold tracking-tight">Learner practice</h2>
      <p className="mt-1 text-sm text-slate-600">
        Browse published cases, karaoke with word sync, then 10 shadowing cards.
      </p>

      {progression ? (
        <div className="mt-4 text-sm text-slate-700">
          <p>
            Rank: <span className="font-medium">{progression.rank_label}</span>
            {' · '}
            {progression.cases_completed} cases · {progression.cme_points} CME
          </p>
          {progression.certificates.length > 0 ? (
            <ul className="mt-1 text-xs text-slate-500">
              {progression.certificates.map((cert) => (
                <li key={cert.id}>
                  {cert.title} — share `{cert.share_slug}`
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      ) : null}

      {skillTree.length > 0 ? (
        <div className="mt-4 border-t border-slate-200 pt-4">
          <h3 className="text-base font-semibold">Specialty skill tree</h3>
          <p className="mt-1 text-sm text-slate-500">
            Finish Nhi đại cương before Tim mạch nhi unlocks.
          </p>
          <ul className="mt-3 space-y-2 text-sm">
            {skillTree.map((node) => (
              <li key={node.slug}>
                <SkillNodeView node={node} />
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      <div className="mt-4 grid gap-3 text-sm">
        <label>
          Lessons / week
          <input
            type="number"
            min={1}
            max={14}
            className="mt-1 w-full rounded border border-slate-300 px-2 py-1"
            value={lessonsPerWeek}
            onChange={(e) => setLessonsPerWeek(Number(e.target.value))}
          />
        </label>
        <label>
          CEFR package
          <select
            className="mt-1 w-full rounded border border-slate-300 px-2 py-1"
            value={cefrPackage}
            onChange={(e) => setCefrPackage(e.target.value as CefrLevel)}
          >
            <option value="A2">A2</option>
            <option value="B1">B1</option>
            <option value="C1">C1</option>
          </select>
        </label>
        <button
          type="button"
          onClick={() => void onSaveProfile()}
          className="w-fit rounded-md bg-slate-900 px-3 py-2 text-sm font-medium text-white hover:bg-slate-800"
        >
          Save 6-month path
        </button>
      </div>

      {cases.length === 0 ? (
        <p className="mt-4 text-sm text-slate-500">
          No published cases yet. Ask an editor to publish one.
        </p>
      ) : (
        <div className="mt-6 flex flex-col gap-3">
          <label className="text-sm">
            Published case
            <select
              className="mt-1 w-full rounded border border-slate-300 px-2 py-1"
              value={caseId ?? ''}
              onChange={(e) => setCaseId(Number(e.target.value))}
            >
              {cases.map((c) => (
                <option key={c.id} value={c.id} disabled={c.unlocked === false}>
                  #{c.id} — {c.title}
                  {c.unlocked === false ? ` (locked: ${c.unlock_reason})` : ''}
                </option>
              ))}
            </select>
          </label>
          <label className="text-sm">
            Dialogue
            <select
              className="mt-1 w-full rounded border border-slate-300 px-2 py-1"
              value={dialogueId ?? ''}
              onChange={(e) => setDialogueId(Number(e.target.value))}
            >
              {dialogues.map((d) => (
                <option key={d.id} value={d.id}>
                  #{d.id} — {d.context} ({d.cefr_level})
                </option>
              ))}
            </select>
          </label>
        </div>
      )}

      {lesson ? (
        <div className="mt-6">
          <div className="rounded-lg bg-gradient-to-br from-teal-50 via-white to-orange-50 p-4">
            <p className="text-xs uppercase tracking-wide text-slate-500">
              Clinic scene
            </p>
            <h3 className="mt-1 text-lg font-semibold">{lesson.title}</h3>
            <p className="mt-1 text-xs text-slate-500">
              ISBN {lesson.isbn} · edition {lesson.edition}
              {lesson.citation_pages.length
                ? ` · pages ${lesson.citation_pages.join(', ')}`
                : ''}
            </p>

            <div className="mt-4 flex flex-wrap items-center gap-3 text-sm">
              <label>
                Speed
                <input
                  type="range"
                  min={0.5}
                  max={1.25}
                  step={0.05}
                  value={speed}
                  onChange={(e) => setSpeed(Number(e.target.value))}
                  className="ml-2 align-middle"
                />
                <span className="ml-2">{speed.toFixed(2)}×</span>
              </label>
              <label className="flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={showVi}
                  onChange={(e) => setShowVi(e.target.checked)}
                />
                Show VI gloss
              </label>
            </div>

            {current ? (
              <div className="mt-4">
                <p className={`font-medium ${speakerColor}`}>{current.speaker}</p>
                <p className="mt-2 text-base leading-relaxed">
                  {current.timestamps.map((stamp, idx) => (
                    <span
                      key={`${stamp.word}-${idx}`}
                      className={
                        idx === activeWord
                          ? 'bg-teal-200 text-teal-950'
                          : undefined
                      }
                    >
                      {stamp.word}{' '}
                    </span>
                  ))}
                </p>
                {showVi && current.text_vi ? (
                  <p className="mt-1 text-sm text-slate-600">{current.text_vi}</p>
                ) : null}
                <audio ref={audioRef} controls className="mt-3 w-full" />
                <div className="mt-2 flex gap-2">
                  <button
                    type="button"
                    className="text-sm underline"
                    disabled={lineIndex <= 0}
                    onClick={() => setLineIndex((v) => Math.max(0, v - 1))}
                  >
                    Prev line
                  </button>
                  <button
                    type="button"
                    className="text-sm underline"
                    disabled={lineIndex >= lesson.playlist.length - 1}
                    onClick={() =>
                      setLineIndex((v) =>
                        Math.min(lesson.playlist.length - 1, v + 1),
                      )
                    }
                  >
                    Next line
                  </button>
                </div>
              </div>
            ) : null}
          </div>

          <div className="mt-6">
            <h3 className="text-base font-semibold">Shadowing (10 cards)</h3>
            <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2">
              {cards.map((card) => (
                <button
                  key={card.card_index}
                  type="button"
                  onClick={() => setCardIndex(card.card_index)}
                  className={`border-l-2 pl-3 text-left text-sm ${
                    card.card_index === cardIndex
                      ? 'border-orange-500'
                      : 'border-slate-300'
                  }`}
                >
                  <p className="font-medium">{card.speaker}</p>
                  <p className="text-slate-700">{card.text}</p>
                </button>
              ))}
            </div>
          </div>

          <div className="mt-6 border-t border-slate-200 pt-4">
            <h3 className="text-base font-semibold">Role-play</h3>
            <div className="mt-2 flex flex-wrap gap-3 text-sm">
              <label className="flex items-center gap-2">
                <input
                  type="radio"
                  name="response-mode"
                  checked={responseMode === 'read_along'}
                  onChange={() => setResponseMode('read_along')}
                />
                Read-along
              </label>
              <label className="flex items-center gap-2">
                <input
                  type="radio"
                  name="response-mode"
                  checked={responseMode === 'free_speech'}
                  onChange={() => setResponseMode('free_speech')}
                />
                Free response (+ empathy)
              </label>
            </div>
            <div className="mt-3 grid gap-3 sm:grid-cols-2">
              <div className="border-l-2 border-teal-600 pl-3 text-sm">
                <p className="font-medium">AI script</p>
                <p className="mt-1 text-slate-600">
                  {current?.text ?? 'Select a dialogue line'}
                </p>
              </div>
              <div className="border-l-2 border-orange-500 pl-3 text-sm">
                <p className="font-medium">Your mic</p>
                <p className="mt-1 text-slate-500">
                  {responseMode === 'read_along'
                    ? 'Match the script. Word colors: green / yellow / red.'
                    : 'Respond freely. Empathy rubric applies (practice aid only).'}
                </p>
                <button
                  type="button"
                  disabled={uploadingAttempt}
                  className="mt-2 rounded-md border border-slate-300 px-3 py-1.5 text-sm font-medium disabled:opacity-50"
                  onClick={() => void onToggleMicRecord()}
                >
                  {recording
                    ? 'Stop & score'
                    : uploadingAttempt
                      ? 'Scoring…'
                      : 'Record attempt'}
                </button>
                {lastScore ? (
                  <div className="mt-3 space-y-2">
                    <p className="text-xs text-slate-500">
                      Engine: {lastScore.engine}
                      {lastScore.stress_hint
                        ? ` · ${lastScore.stress_hint}`
                        : ''}
                      {' · '}
                      tap a red word to hear the AI sample
                    </p>
                    <p className="flex flex-wrap gap-x-1 gap-y-1 text-sm leading-relaxed">
                      {lastScore.words.map((word, index) =>
                        word.band === 'red' ? (
                          <button
                            key={`${word.word}-${index}`}
                            type="button"
                            className="text-red-600 underline"
                            title={`${word.accuracy} — replay AI`}
                            onClick={() => void onReplayRedWord(word.word)}
                          >
                            {word.word}
                          </button>
                        ) : (
                          <span
                            key={`${word.word}-${index}`}
                            className={
                              word.band === 'green'
                                ? 'text-emerald-700'
                                : 'text-amber-600'
                            }
                            title={`${word.accuracy}`}
                          >
                            {word.word}
                          </span>
                        ),
                      )}
                    </p>
                  </div>
                ) : null}
                {lastEmpathy ? (
                  <div className="mt-3 text-sm">
                    <p className="font-medium">
                      Empathy {lastEmpathy.score} ({lastEmpathy.engine})
                    </p>
                    <p className="mt-1 text-slate-600">{lastEmpathy.feedback}</p>
                    <p className="mt-1 text-xs text-slate-500">
                      {lastEmpathy.disclaimer}
                    </p>
                  </div>
                ) : null}
              </div>
            </div>
          </div>

          <div className="mt-6 border-t border-slate-200 pt-4">
            <h3 className="text-base font-semibold">SRS queue (T+1)</h3>
            <p className="mt-1 text-sm text-slate-500">
              Weak words from PA land here for review the next day.
            </p>
            {srsCards.length === 0 ? (
              <p className="mt-2 text-sm text-slate-500">No cards due yet.</p>
            ) : (
              <ul className="mt-3 space-y-2">
                {srsCards.map((card) => (
                  <li
                    key={card.id}
                    className="flex items-center justify-between gap-3 text-sm"
                  >
                    <span>
                      <span
                        className={
                          card.band === 'red' ? 'text-red-600' : 'text-amber-600'
                        }
                      >
                        {card.phrase}
                      </span>
                      <span className="ml-2 text-xs text-slate-500">
                        due {card.due_at}
                      </span>
                    </span>
                    <button
                      type="button"
                      className="underline"
                      onClick={() => {
                        void (async () => {
                          try {
                            await completeSrsCard(card.id)
                            await refreshSrs()
                          } catch (err) {
                            onError(
                              err instanceof Error
                                ? err.message
                                : 'Failed to complete card',
                            )
                          }
                        })()
                      }}
                    >
                      Done
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>

          <button
            type="button"
            onClick={() => void onComplete()}
            className="mt-4 rounded-md bg-teal-700 px-3 py-2 text-sm font-medium text-white hover:bg-teal-600"
          >
            Mark karaoke + shadowing complete
          </button>
        </div>
      ) : null}

      {note ? <p className="mt-3 text-sm text-slate-600">{note}</p> : null}
    </section>
  )
}

function SkillNodeView({ node, depth = 0 }: { node: SkillTreeNode; depth?: number }) {
  return (
    <div style={{ marginLeft: depth * 12 }}>
      <p
        className={
          node.unlocked
            ? node.completed
              ? 'text-emerald-700'
              : 'text-slate-800'
            : 'text-slate-400'
        }
      >
        {node.title}
        {node.completed ? ' ✓' : ''}
        {!node.unlocked && node.unlock_reason
          ? ` — ${node.unlock_reason}`
          : ''}
        {node.case_ids.length > 0
          ? ` (${node.case_ids.length} case${node.case_ids.length > 1 ? 's' : ''})`
          : ''}
      </p>
      {node.children.length > 0 ? (
        <ul className="mt-1 space-y-1">
          {node.children.map((child) => (
            <li key={child.slug}>
              <SkillNodeView node={child} depth={depth + 1} />
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  )
}
