import { useEffect, useMemo, useRef, useState } from 'react'
import {
  certificateShareUrl,
  completeLesson,
  completeSrsCard,
  exportDialogueVideo,
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
  persistDialogueOfflineCache,
  synthesizeEmpathySample,
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
import { ensureMicrophonePermission, isNativePlatform } from './mobile'
import { resolveLessonAudioUrl } from './offlineCache'
import { peakStressIndexes, stressPatternAligns } from './stressHighlight'

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
  const karaokeRegionRef = useRef<HTMLDivElement | null>(null)
  const mediaRecorderRef = useRef<MediaRecorder | null>(null)
  const mediaChunksRef = useRef<Blob[]>([])
  const mediaStreamRef = useRef<MediaStream | null>(null)

  const current = lesson?.playlist[lineIndex] ?? null
  const stressPeaks = useMemo(() => {
    if (!current || lesson?.cefr_level !== 'C1') return new Set<number>()
    if (!stressPatternAligns(current.stress_pattern, current.timestamps.length)) {
      return new Set<number>()
    }
    return peakStressIndexes(current.stress_pattern)
  }, [current, lesson?.cefr_level])

  const stressedWordsLabel = useMemo(() => {
    if (!current || stressPeaks.size === 0) return ''
    return [...stressPeaks]
      .map((i) => current.timestamps[i]?.word)
      .filter(Boolean)
      .join(', ')
  }, [current, stressPeaks])

  const karaokeLiveLabel = current
    ? [
        `Line ${lineIndex + 1} of ${lesson?.playlist.length ?? 0}.`,
        `${current.speaker}: ${current.text}`,
        stressedWordsLabel ? `Primary stress on: ${stressedWordsLabel}.` : '',
      ]
        .filter(Boolean)
        .join(' ')
    : ''
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
        if (navigator.onLine) {
          void persistDialogueOfflineCache(dialogueId, lessonBody, shadowCards)
        }
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
    if (!audio || !current || dialogueId == null) return
    let revoked: string | null = null
    let cancelled = false
    audio.pause()
    ;(async () => {
      const src = await resolveLessonAudioUrl(
        dialogueId,
        lineIndex,
        current.audio_url,
      )
      if (cancelled) {
        if (src.startsWith('blob:')) URL.revokeObjectURL(src)
        return
      }
      if (src.startsWith('blob:')) revoked = src
      audio.src = src
      audio.playbackRate = speed
      setActiveWord(-1)
    })()
    return () => {
      cancelled = true
      if (revoked) URL.revokeObjectURL(revoked)
    }
  }, [current, speed, dialogueId, lineIndex])

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

  useEffect(() => {
    const region = karaokeRegionRef.current
    if (!region || !lesson) return

    const onKeyDown = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null
      if (
        target &&
        (target.tagName === 'INPUT' ||
          target.tagName === 'TEXTAREA' ||
          target.tagName === 'SELECT' ||
          target.isContentEditable)
      ) {
        return
      }
      if (!region.contains(document.activeElement) && document.activeElement !== region) {
        return
      }
      const last = lesson.playlist.length - 1
      if (event.key === 'ArrowLeft') {
        event.preventDefault()
        setLineIndex((v) => Math.max(0, v - 1))
      } else if (event.key === 'ArrowRight') {
        event.preventDefault()
        setLineIndex((v) => Math.min(last, v + 1))
      } else if (event.key === 'Home') {
        event.preventDefault()
        setLineIndex(0)
      } else if (event.key === 'End') {
        event.preventDefault()
        setLineIndex(last)
      }
    }

    region.addEventListener('keydown', onKeyDown)
    return () => region.removeEventListener('keydown', onKeyDown)
  }, [lesson])

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

  async function onExportVideo() {
    if (dialogueId == null) return
    onError(null)
    try {
      setNote('Exporting 1080p MP4…')
      const job = await exportDialogueVideo(dialogueId, 'remotion')
      if (job.status === 'succeeded' && job.download_url) {
        setNote(`Export ready (${job.width}×${job.height}, ${job.engine})`)
        window.open(job.download_url, '_blank', 'noopener,noreferrer')
      } else if (job.status === 'failed') {
        onError(job.error ?? 'Export failed')
      } else {
        setNote(`Export ${job.status}`)
      }
    } catch (err) {
      onError(err instanceof Error ? err.message : 'Export failed')
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
      if (isNativePlatform()) {
        const ok = await ensureMicrophonePermission()
        if (!ok) {
          onError('Microphone permission denied. Enable mic for LearnEnglish in system settings.')
          return
        }
      }
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
            {' · '}
            streak {progression.streak_days ?? 0}d
          </p>
          {progression.certificates.length > 0 ? (
            <ul className="mt-1 space-y-1 text-xs text-slate-500">
              {progression.certificates.map((cert) => (
                <li key={cert.id} className="flex flex-wrap items-center gap-2">
                  <span>{cert.title}</span>
                  <button
                    type="button"
                    className="underline"
                    onClick={() => {
                      const url = certificateShareUrl(cert.share_slug)
                      void navigator.clipboard.writeText(url).then(
                        () => setNote(`Copied share link for ${cert.title}`),
                        () => setNote(url),
                      )
                    }}
                  >
                    Copy share link
                  </button>
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
          <div
            ref={karaokeRegionRef}
            role="region"
            aria-labelledby="karaoke-heading"
            tabIndex={0}
            className="rounded-lg bg-gradient-to-br from-teal-50 via-white to-orange-50 p-4 outline-none focus-visible:ring-2 focus-visible:ring-teal-700 focus-visible:ring-offset-2"
          >
            <p className="text-xs uppercase tracking-wide text-slate-500">
              Clinic scene
            </p>
            <h3 id="karaoke-heading" className="mt-1 text-lg font-semibold">
              {lesson.title}
            </h3>
            <p className="mt-1 text-xs text-slate-500">
              ISBN {lesson.isbn} · edition {lesson.edition}
              {lesson.citation_pages.length
                ? ` · pages ${lesson.citation_pages.join(', ')}`
                : ''}
            </p>
            <p className="mt-2 text-xs text-slate-600">
              Keyboard: focus this player, then ← / → for lines, Home / End for
              first / last.
            </p>

            <div className="mt-4 flex flex-wrap items-center gap-3 text-sm">
              <label htmlFor="karaoke-speed" className="flex items-center gap-2">
                Speed
                <input
                  id="karaoke-speed"
                  type="range"
                  min={0.5}
                  max={1.25}
                  step={0.05}
                  value={speed}
                  onChange={(e) => setSpeed(Number(e.target.value))}
                  className="align-middle"
                  aria-valuetext={`${speed.toFixed(2)} times`}
                />
                <span aria-hidden="true">{speed.toFixed(2)}×</span>
              </label>
              <label htmlFor="karaoke-show-vi" className="flex items-center gap-2">
                <input
                  id="karaoke-show-vi"
                  type="checkbox"
                  checked={showVi}
                  onChange={(e) => setShowVi(e.target.checked)}
                />
                Show VI gloss
              </label>
            </div>

            {lesson.session_kind === 'presentation' ? (
              <div className="mt-3">
                <p className="text-xs text-slate-500" id="karaoke-progress-label">
                  ~10 min presentation · line {lineIndex + 1}/
                  {lesson.playlist.length}
                  {lesson.estimated_seconds
                    ? ` · ~${Math.round(lesson.estimated_seconds / 60)} min script`
                    : ''}
                </p>
                <div
                  className="mt-1 h-1.5 w-full overflow-hidden rounded bg-slate-200"
                  role="progressbar"
                  aria-labelledby="karaoke-progress-label"
                  aria-valuenow={lineIndex + 1}
                  aria-valuemin={1}
                  aria-valuemax={lesson.playlist.length}
                >
                  <div
                    className="h-full bg-teal-700 transition-[width] duration-300"
                    style={{
                      width: `${Math.min(
                        100,
                        ((lineIndex + 1) / Math.max(lesson.playlist.length, 1)) *
                          100,
                      )}%`,
                    }}
                  />
                </div>
              </div>
            ) : null}

            {current ? (
              <div className="mt-4">
                <p
                  className={`font-medium ${speakerColor}`}
                  aria-live="polite"
                  aria-atomic="true"
                >
                  {karaokeLiveLabel}
                </p>
                <p className="mt-2 text-base leading-relaxed text-slate-900" aria-hidden="true">
                  {current.timestamps.map((stamp, idx) => {
                    const isActive = idx === activeWord
                    const isStressed = stressPeaks.has(idx)
                    let className: string | undefined
                    if (isActive) {
                      className =
                        'rounded-sm bg-teal-800 px-0.5 font-semibold text-white'
                    } else if (isStressed) {
                      className =
                        'font-semibold text-teal-900 underline decoration-teal-700 decoration-2 underline-offset-2'
                    }
                    return (
                      <span key={`${stamp.word}-${idx}`} className={className}>
                        {stamp.word}{' '}
                      </span>
                    )
                  })}
                </p>
                {stressedWordsLabel ? (
                  <p className="mt-1 text-xs text-slate-600">
                    C1 stress: underline marks primary stress (
                    {stressedWordsLabel})
                  </p>
                ) : null}
                {showVi && current.text_vi ? (
                  <p className="mt-1 text-sm text-slate-700">{current.text_vi}</p>
                ) : null}
                <audio
                  ref={audioRef}
                  controls
                  className="mt-3 w-full"
                  aria-label={`Audio for line ${lineIndex + 1}`}
                />
                <div className="mt-2 flex gap-2">
                  <button
                    type="button"
                    className="rounded-sm text-sm underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-teal-800 disabled:opacity-40"
                    disabled={lineIndex <= 0}
                    onClick={() => setLineIndex((v) => Math.max(0, v - 1))}
                  >
                    Prev line
                  </button>
                  <button
                    type="button"
                    className="rounded-sm text-sm underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-teal-800 disabled:opacity-40"
                    disabled={lineIndex >= lesson.playlist.length - 1}
                    onClick={() =>
                      setLineIndex((v) =>
                        Math.min(lesson.playlist.length - 1, v + 1),
                      )
                    }
                  >
                    Next line
                  </button>
                  <span className="text-sm text-slate-600" aria-live="polite">
                    Line {lineIndex + 1} of {lesson.playlist.length}
                  </span>
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
                            className="text-red-700 underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-red-800"
                            title={`${word.accuracy} — replay AI`}
                            aria-label={`Replay AI sample for ${word.word}, accuracy ${word.accuracy}`}
                            onClick={() => void onReplayRedWord(word.word)}
                          >
                            {word.word}
                          </button>
                        ) : (
                          <span
                            key={`${word.word}-${index}`}
                            className={
                              word.band === 'green'
                                ? 'text-emerald-800'
                                : 'text-amber-800'
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
                    {lastEmpathy.coaching_tip ? (
                      <div className="mt-2 border-l-2 border-amber-500 pl-2">
                        <p className="font-medium text-amber-900">
                          Intonation tip
                        </p>
                        <p className="mt-0.5 text-slate-600">
                          {lastEmpathy.coaching_tip}
                        </p>
                        {lastEmpathy.sample_phrase ? (
                          <>
                            <p className="mt-1 italic text-slate-700">
                              “{lastEmpathy.sample_phrase}”
                            </p>
                            <button
                              type="button"
                              className="mt-1 underline"
                              onClick={() => {
                                void (async () => {
                                  try {
                                    onError(null)
                                    const sample = await synthesizeEmpathySample(
                                      lastEmpathy.sample_phrase!,
                                    )
                                    const audio = new Audio(sample.audio_url)
                                    await audio.play()
                                  } catch (err) {
                                    onError(
                                      err instanceof Error
                                        ? err.message
                                        : 'Could not play sample',
                                    )
                                  }
                                })()
                              }}
                            >
                              Play sample tone
                            </button>
                          </>
                        ) : null}
                      </div>
                    ) : null}
                    <p className="mt-1 text-xs text-slate-500">
                      {lastEmpathy.disclaimer}
                    </p>
                  </div>
                ) : null}
              </div>
            </div>
          </div>

          <div className="mt-6 border-t border-slate-200 pt-4">
            <h3 className="text-base font-semibold">SRS queue</h3>
            <p className="mt-1 text-sm text-slate-500">
              Weak PA words for spaced review (1→3→7→14 days after each Done).
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
                        next review {card.due_at}
                        {typeof card.repetition === 'number'
                          ? ` · rep ${card.repetition}`
                          : ''}
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

          <div className="mt-4 flex flex-wrap gap-2">
            <button
              type="button"
              onClick={() => void onComplete()}
              className="rounded-md bg-teal-700 px-3 py-2 text-sm font-medium text-white hover:bg-teal-600"
            >
              Mark karaoke + shadowing complete
            </button>
            <button
              type="button"
              onClick={() => void onExportVideo()}
              className="rounded-md border border-slate-300 px-3 py-2 text-sm font-medium text-slate-800 hover:bg-slate-100"
            >
              Export 1080p MP4
            </button>
          </div>
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
