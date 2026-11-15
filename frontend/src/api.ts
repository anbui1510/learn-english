import {
  cacheDialogueOffline,
  isBrowserOffline,
  readCachedDialogue,
} from './offlineCache'

const API_BASE =
  import.meta.env.VITE_API_BASE_URL?.replace(/\/$/, '') ??
  'http://127.0.0.1:8000'

export type Role = 'admin' | 'editor' | 'learner'

export type AuthUser = {
  id: number
  sub: string
  email: string
  name: string | null
  role: Role
}

export type AdminUser = {
  id: number
  email: string
  name: string | null
  role: Role
  google_sub: string
}

export function loginUrl(returnTo?: string): string {
  const base = `${API_BASE}/auth/google/login`
  if (!returnTo) return base
  const url = new URL(base)
  url.searchParams.set('return_to', returnTo)
  return url.toString()
}

/** Capacitor deep-link target used after Google OAuth (Custom Tab / Browser). */
export const MOBILE_AUTH_RETURN_URI = 'com.learnenglish.app://auth/callback'

export async function exchangeAuthCode(code: string): Promise<void> {
  const response = await fetch(`${API_BASE}/auth/exchange`, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ code }),
  })
  if (!response.ok) {
    throw new Error(`Auth exchange failed (${response.status})`)
  }
}

export async function fetchMe(): Promise<AuthUser | null> {
  const response = await fetch(`${API_BASE}/auth/me`, {
    credentials: 'include',
  })
  if (response.status === 401) {
    return null
  }
  if (!response.ok) {
    throw new Error(`Failed to load session (${response.status})`)
  }
  return (await response.json()) as AuthUser
}

export async function logout(): Promise<void> {
  const response = await fetch(`${API_BASE}/auth/logout`, {
    method: 'POST',
    credentials: 'include',
  })
  if (!response.ok) {
    throw new Error(`Logout failed (${response.status})`)
  }
}

export async function listUsers(): Promise<AdminUser[]> {
  const response = await fetch(`${API_BASE}/admin/users`, {
    credentials: 'include',
  })
  if (!response.ok) {
    throw new Error(`Failed to list users (${response.status})`)
  }
  return (await response.json()) as AdminUser[]
}

export async function assignRole(
  userId: number,
  role: Role,
): Promise<AdminUser> {
  const response = await fetch(`${API_BASE}/admin/users/${userId}/role`, {
    method: 'PATCH',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ role }),
  })
  if (!response.ok) {
    throw new Error(`Failed to assign role (${response.status})`)
  }
  return (await response.json()) as AdminUser
}

export type PaUsageRow = {
  user_id: number
  email: string | null
  usage_day: string
  score_count: number
  estimated_cost_usd: number
}

export async function fetchPaUsage(days = 14): Promise<PaUsageRow[]> {
  const response = await fetch(`${API_BASE}/admin/pa-usage?days=${days}`, {
    credentials: 'include',
  })
  if (!response.ok) {
    throw new Error(`Failed to load PA usage (${response.status})`)
  }
  return (await response.json()) as PaUsageRow[]
}

export type ExtractStatus =
  | 'none'
  | 'queued'
  | 'running'
  | 'succeeded'
  | 'failed'

export type CaseDraft = {
  id: number
  owner_user_id: number
  title: string
  status: string
  isbn: string | null
  edition: string | null
  book_source_id?: number | null
  book_source_slug?: string | null
  pdf_object_key: string | null
  pdf_byte_size: number | null
  extract_status: ExtractStatus
  extract_error: string | null
  published_at: string | null
  published_by_user_id: number | null
  module_slug?: string | null
  unlock_cme_points?: number
  unlock_rank?: string | null
  unlock_requires_case_id?: number | null
  unlock_requires_streak_days?: number
}

export type BookSource = {
  id: number
  slug: string
  title: string
  publisher?: string | null
  default_isbn?: string | null
  notes?: string | null
}

export type TtsProvider = 'synthetic' | 'edge' | 'azure' | 'elevenlabs'

export type TtsSettings = {
  provider: TtsProvider
  premium_enabled: boolean
  updated_at?: string | null
  notes?: string
}

export async function fetchTtsSettings(): Promise<TtsSettings> {
  const response = await fetch(`${API_BASE}/admin/tts-settings`, {
    credentials: 'include',
  })
  if (!response.ok) {
    throw new Error(`Failed to load TTS settings (${response.status})`)
  }
  return (await response.json()) as TtsSettings
}

export async function patchTtsSettings(input: {
  provider?: TtsProvider
  premium_enabled?: boolean
}): Promise<TtsSettings> {
  const response = await fetch(`${API_BASE}/admin/tts-settings`, {
    method: 'PATCH',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(input),
  })
  if (!response.ok) {
    throw new Error(`Failed to update TTS settings (${response.status})`)
  }
  return (await response.json()) as TtsSettings
}

export async function listAdminBookSources(): Promise<BookSource[]> {
  const response = await fetch(`${API_BASE}/admin/book-sources`, {
    credentials: 'include',
  })
  if (!response.ok) {
    throw new Error(`Failed to list book sources (${response.status})`)
  }
  return (await response.json()) as BookSource[]
}

export async function createBookSource(input: {
  slug: string
  title: string
  publisher?: string
  default_isbn?: string
  notes?: string
}): Promise<BookSource> {
  const response = await fetch(`${API_BASE}/admin/book-sources`, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(input),
  })
  if (!response.ok) {
    throw new Error(`Failed to create book source (${response.status})`)
  }
  return (await response.json()) as BookSource
}

export async function listEditorBookSources(): Promise<BookSource[]> {
  const response = await fetch(`${API_BASE}/editor/book-sources`, {
    credentials: 'include',
  })
  if (!response.ok) {
    throw new Error(`Failed to list book sources (${response.status})`)
  }
  return (await response.json()) as BookSource[]
}

export type ClinicalFact = {
  id: number
  case_id: number
  source_quote: string
  atomic_fact: string
  category: string
  status: 'needs_review' | 'verified' | 'rejected'
  page: number
  section: string | null
  isbn: string
  edition: string
}

export async function uploadCasePdf(input: {
  title: string
  isbn: string
  edition: string
  file: File
  bookSourceId?: number | null
}): Promise<CaseDraft> {
  const body = new FormData()
  body.set('title', input.title)
  body.set('isbn', input.isbn)
  body.set('edition', input.edition)
  body.set('file', input.file)
  if (input.bookSourceId != null) {
    body.set('book_source_id', String(input.bookSourceId))
  }
  const response = await fetch(`${API_BASE}/editor/cases/upload`, {
    method: 'POST',
    credentials: 'include',
    body,
  })
  if (!response.ok) {
    throw new Error(`Upload failed (${response.status})`)
  }
  return (await response.json()) as CaseDraft
}

export async function listMyCases(): Promise<CaseDraft[]> {
  const response = await fetch(`${API_BASE}/editor/cases`, {
    credentials: 'include',
  })
  if (!response.ok) {
    throw new Error(`Failed to list cases (${response.status})`)
  }
  return (await response.json()) as CaseDraft[]
}

export async function getCase(caseId: number): Promise<CaseDraft> {
  const response = await fetch(`${API_BASE}/editor/cases/${caseId}`, {
    credentials: 'include',
  })
  if (!response.ok) {
    throw new Error(`Failed to load case (${response.status})`)
  }
  return (await response.json()) as CaseDraft
}

export async function startExtract(
  caseId: number,
): Promise<{ case_id: number; extract_status: ExtractStatus }> {
  const response = await fetch(`${API_BASE}/editor/cases/${caseId}/extract`, {
    method: 'POST',
    credentials: 'include',
  })
  if (!response.ok) {
    throw new Error(`Extract failed (${response.status})`)
  }
  return (await response.json()) as {
    case_id: number
    extract_status: ExtractStatus
  }
}

export async function listCaseFacts(
  caseId: number,
  filters?: { status?: string; category?: string },
): Promise<ClinicalFact[]> {
  const params = new URLSearchParams()
  if (filters?.status) params.set('status', filters.status)
  if (filters?.category) params.set('category', filters.category)
  const qs = params.toString()
  const response = await fetch(
    `${API_BASE}/editor/cases/${caseId}/facts${qs ? `?${qs}` : ''}`,
    { credentials: 'include' },
  )
  if (!response.ok) {
    throw new Error(`Failed to list facts (${response.status})`)
  }
  return (await response.json()) as ClinicalFact[]
}

export async function patchCaseFact(
  caseId: number,
  factId: number,
  body: {
    status?: ClinicalFact['status']
    source_quote?: string
    atomic_fact?: string
    category?: string
  },
): Promise<ClinicalFact> {
  const response = await fetch(
    `${API_BASE}/editor/cases/${caseId}/facts/${factId}`,
    {
      method: 'PATCH',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    },
  )
  if (!response.ok) {
    throw new Error(`Fact update failed (${response.status})`)
  }
  return (await response.json()) as ClinicalFact
}

export async function publishCase(caseId: number): Promise<CaseDraft> {
  const response = await fetch(`${API_BASE}/editor/cases/${caseId}/publish`, {
    method: 'POST',
    credentials: 'include',
  })
  if (!response.ok) {
    throw new Error(`Publish failed (${response.status})`)
  }
  return (await response.json()) as CaseDraft
}

export type DialogueContext =
  | 'patient_family'
  | 'colleague_sbar'
  | 'expert_cme'

export type CefrLevel = 'A2' | 'B1' | 'C1'

export type DialogueLine = {
  speaker: string
  text: string
  text_vi?: string
  fact_ids: string[]
  is_key_phrase?: boolean
}

export type DialogueArtifact = {
  id: number
  case_id: number
  context: DialogueContext
  cefr_level: CefrLevel
  estimated_seconds: number
  duration_warning: boolean
  lines: DialogueLine[]
  created_at: string
}

export type SessionKind = 'standard' | 'presentation'

export async function generateDialogues(
  caseId: number,
  input: {
    contexts: DialogueContext[]
    cefr_level: CefrLevel
    include_vi?: boolean
    session_kind?: SessionKind
    target_seconds?: number
  },
): Promise<DialogueArtifact[]> {
  const response = await fetch(
    `${API_BASE}/editor/cases/${caseId}/generate-dialogues`,
    {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(input),
    },
  )
  if (!response.ok) {
    throw new Error(`generate-dialogues failed (${response.status})`)
  }
  return (await response.json()) as DialogueArtifact[]
}

export async function listCaseDialogues(
  caseId: number,
): Promise<DialogueArtifact[]> {
  const response = await fetch(
    `${API_BASE}/editor/cases/${caseId}/dialogues`,
    { credentials: 'include' },
  )
  if (!response.ok) {
    throw new Error(`Failed to list dialogues (${response.status})`)
  }
  return (await response.json()) as DialogueArtifact[]
}

export async function synthesizeDialogue(
  caseId: number,
  dialogueId: number,
): Promise<unknown[]> {
  const response = await fetch(
    `${API_BASE}/editor/cases/${caseId}/dialogues/${dialogueId}/synthesize`,
    { method: 'POST', credentials: 'include' },
  )
  if (!response.ok) {
    throw new Error(`Synthesize failed (${response.status})`)
  }
  return (await response.json()) as unknown[]
}

export type PublishedCase = {
  id: number
  title: string
  isbn: string | null
  edition: string | null
  published_at: string | null
  module_slug?: string | null
  unlocked?: boolean
  unlock_reason?: string | null
}

export type Progression = {
  rank_id: string
  rank_label: string
  cases_completed: number
  cme_points: number
  streak_days?: number
  certificates: {
    id: number
    module_slug: string
    title: string
    cme_points: number
    share_slug: string
    disclaimer: string
  }[]
  ranks: { id: string; label: string; cases_required: number }[]
}

export type WordStamp = {
  word: string
  offset_ms: number
  duration_ms: number
}

export type PlaylistItem = {
  line_index: number
  speaker: string
  voice: string
  text: string
  text_vi?: string | null
  audio_url: string
  duration_ms: number
  timestamps: WordStamp[]
  fact_ids: string[]
}

export type Lesson = {
  case_id: number
  dialogue_id: number
  title: string
  context: string
  cefr_level: string
  isbn: string | null
  edition: string | null
  citation_pages: number[]
  playlist: PlaylistItem[]
  session_kind?: SessionKind
  target_seconds?: number | null
  estimated_seconds?: number
}

export type ShadowingCard = {
  card_index: number
  line_index: number
  speaker: string
  text: string
  text_vi?: string
  fact_ids: string[]
  is_key_phrase: boolean
}

export type LearnerProfile = {
  user_id: number
  lessons_per_week: number
  cefr_package: CefrLevel
  path_months: number
}

export async function listPublishedCases(): Promise<PublishedCase[]> {
  const response = await fetch(`${API_BASE}/learner/cases`, {
    credentials: 'include',
  })
  if (!response.ok) {
    throw new Error(`Failed to list published cases (${response.status})`)
  }
  return (await response.json()) as PublishedCase[]
}

export async function listLearnerCaseDialogues(
  caseId: number,
): Promise<
  { id: number; case_id: number; context: string; cefr_level: string }[]
> {
  const response = await fetch(
    `${API_BASE}/learner/cases/${caseId}/dialogues`,
    { credentials: 'include' },
  )
  if (!response.ok) {
    throw new Error(`Failed to list dialogues (${response.status})`)
  }
  return (await response.json()) as {
    id: number
    case_id: number
    context: string
    cefr_level: string
  }[]
}

export async function fetchLesson(dialogueId: number): Promise<Lesson> {
  try {
    const response = await fetch(
      `${API_BASE}/learner/dialogues/${dialogueId}/lesson`,
      { credentials: 'include' },
    )
    if (!response.ok) {
      throw new Error(`Failed to load lesson (${response.status})`)
    }
    return (await response.json()) as Lesson
  } catch (err) {
    if (isBrowserOffline()) {
      const cached = await readCachedDialogue(dialogueId)
      if (cached) return cached.lesson
    }
    throw err
  }
}

export async function fetchShadowing(
  dialogueId: number,
): Promise<ShadowingCard[]> {
  try {
    const response = await fetch(
      `${API_BASE}/learner/dialogues/${dialogueId}/shadowing`,
      { credentials: 'include' },
    )
    if (!response.ok) {
      throw new Error(`Failed to load shadowing (${response.status})`)
    }
    const body = (await response.json()) as { cards: ShadowingCard[] }
    return body.cards
  } catch (err) {
    if (isBrowserOffline()) {
      const cached = await readCachedDialogue(dialogueId)
      if (cached) return cached.shadowing
    }
    throw err
  }
}

/** After a successful online load, persist lesson for offline karaoke replay. */
export async function persistDialogueOfflineCache(
  dialogueId: number,
  lesson: Lesson,
  shadowing: ShadowingCard[],
): Promise<void> {
  await cacheDialogueOffline(dialogueId, lesson, shadowing)
}

export async function fetchLearnerProfile(): Promise<LearnerProfile> {
  const response = await fetch(`${API_BASE}/learner/profile`, {
    credentials: 'include',
  })
  if (!response.ok) {
    throw new Error(`Failed to load profile (${response.status})`)
  }
  return (await response.json()) as LearnerProfile
}

export async function patchLearnerProfile(body: {
  lessons_per_week?: number
  cefr_package?: CefrLevel
}): Promise<LearnerProfile> {
  const response = await fetch(`${API_BASE}/learner/profile`, {
    method: 'PATCH',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!response.ok) {
    throw new Error(`Failed to update profile (${response.status})`)
  }
  return (await response.json()) as LearnerProfile
}

export async function completeLesson(dialogueId: number): Promise<{
  cme_awarded: number
  rank_label?: string | null
  certificate?: { share_slug: string; title: string } | null
}> {
  const response = await fetch(`${API_BASE}/learner/completions`, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ dialogue_id: dialogueId }),
  })
  if (!response.ok) {
    throw new Error(`Failed to complete lesson (${response.status})`)
  }
  return (await response.json()) as {
    cme_awarded: number
    rank_label?: string | null
    certificate?: { share_slug: string; title: string } | null
  }
}

export async function fetchProgression(): Promise<Progression> {
  const response = await fetch(`${API_BASE}/learner/progression`, {
    credentials: 'include',
  })
  if (!response.ok) {
    throw new Error(`Failed to load progression (${response.status})`)
  }
  return (await response.json()) as Progression
}

export type SkillTreeNode = {
  slug: string
  title: string
  parent_slug: string | null
  unlocked: boolean
  completed: boolean
  unlock_reason?: string | null
  case_ids: number[]
  children: SkillTreeNode[]
}

export async function fetchSkillTree(): Promise<SkillTreeNode[]> {
  const response = await fetch(`${API_BASE}/learner/skill-tree`, {
    credentials: 'include',
  })
  if (!response.ok) {
    throw new Error(`Failed to load skill tree (${response.status})`)
  }
  const body = (await response.json()) as { nodes: SkillTreeNode[] }
  return body.nodes
}

export type WordReplay = {
  dialogue_id: number
  line_index: number
  word: string
  audio_url: string
  start_ms: number
  end_ms: number
  duration_ms: number
}

export async function fetchWordReplay(input: {
  dialogueId: number
  lineIndex: number
  word: string
}): Promise<WordReplay> {
  const word = encodeURIComponent(input.word)
  const response = await fetch(
    `${API_BASE}/learner/dialogues/${input.dialogueId}/lines/${input.lineIndex}/words/${word}/replay`,
    { credentials: 'include' },
  )
  if (!response.ok) {
    throw new Error(`Word replay failed (${response.status})`)
  }
  return (await response.json()) as WordReplay
}

export async function patchCaseProgression(
  caseId: number,
  body: {
    module_slug?: string | null
    unlock_cme_points?: number
    unlock_rank?: string | null
    unlock_requires_case_id?: number | null
    clear_unlock_requires_case?: boolean
    unlock_requires_streak_days?: number
  },
): Promise<CaseDraft> {
  const response = await fetch(`${API_BASE}/editor/cases/${caseId}/progression`, {
    method: 'PATCH',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!response.ok) {
    throw new Error(`Failed to update progression (${response.status})`)
  }
  return (await response.json()) as CaseDraft
}

export type WordBand = 'green' | 'yellow' | 'red'

export type AttemptScore = {
  engine: string
  pronunciation: number
  completeness: number
  prosody: number
  words: { word: string; accuracy: number; band: WordBand }[]
  stress_hint?: string | null
}

export type EmpathyScore = {
  engine: string
  score: number
  rubric: Record<string, number>
  feedback: string
  disclaimer: string
  coaching_tip?: string | null
  sample_phrase?: string | null
}

export type SharedCertificate = {
  title: string
  module_slug: string
  cme_points: number
  rank_at_issue: string
  share_slug: string
  disclaimer: string
  created_at: string
}

export async function fetchSharedCertificate(
  shareSlug: string,
): Promise<SharedCertificate> {
  const response = await fetch(
    `${API_BASE}/learner/certificates/${encodeURIComponent(shareSlug)}`,
  )
  if (!response.ok) {
    throw new Error(`Certificate not found (${response.status})`)
  }
  return (await response.json()) as SharedCertificate
}

export async function synthesizeEmpathySample(
  text: string,
): Promise<{ text: string; audio_url: string; duration_ms: number }> {
  const response = await fetch(`${API_BASE}/learner/empathy/sample-audio`, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text }),
  })
  if (!response.ok) {
    throw new Error(`Failed to synthesize sample (${response.status})`)
  }
  return (await response.json()) as {
    text: string
    audio_url: string
    duration_ms: number
  }
}

export function certificateShareUrl(shareSlug: string): string {
  const url = new URL(window.location.href)
  url.searchParams.set('cert', shareSlug)
  return url.toString()
}

export type AttemptResult = {
  id: number
  case_id: number
  dialogue_id: number
  mode: string
  response_mode?: string
  score?: AttemptScore | null
  empathy?: EmpathyScore | null
  scored_at?: string | null
  pa_usage?: { used: number; limit: number } | null
  srs_enqueued?: number
}

export type SrsCard = {
  id: number
  phrase: string
  band: string
  due_at: string
  source_attempt_id?: number | null
}

export async function uploadAttemptAudio(input: {
  dialogueId: number
  mode: 'shadowing' | 'role_play'
  file: Blob
  lineIndex?: number
  score?: boolean
  responseMode?: 'read_along' | 'free_speech'
}): Promise<AttemptResult> {
  const body = new FormData()
  body.set('dialogue_id', String(input.dialogueId))
  body.set('mode', input.mode)
  body.set('line_index', String(input.lineIndex ?? 0))
  body.set('score', input.score === false ? 'false' : 'true')
  body.set('response_mode', input.responseMode ?? 'read_along')
  body.set('file', input.file, 'attempt.webm')
  const response = await fetch(`${API_BASE}/learner/attempts/audio`, {
    method: 'POST',
    credentials: 'include',
    body,
  })
  if (!response.ok) {
    throw new Error(`Attempt upload failed (${response.status})`)
  }
  return (await response.json()) as AttemptResult
}

export async function fetchSrsQueue(horizonDays = 1): Promise<SrsCard[]> {
  const response = await fetch(
    `${API_BASE}/learner/srs/queue?horizon_days=${horizonDays}`,
    { credentials: 'include' },
  )
  if (!response.ok) {
    throw new Error(`Failed to load SRS queue (${response.status})`)
  }
  return (await response.json()) as SrsCard[]
}

export async function completeSrsCard(cardId: number): Promise<void> {
  const response = await fetch(`${API_BASE}/learner/srs/${cardId}/done`, {
    method: 'POST',
    credentials: 'include',
  })
  if (!response.ok) {
    throw new Error(`Failed to complete SRS card (${response.status})`)
  }
}

export type VideoExportJob = {
  id: number
  dialogue_id: number
  case_id: number
  status: string
  download_url?: string | null
  error?: string | null
  width: number
  height: number
  engine: string
  created_at: string
  finished_at?: string | null
}

export async function exportDialogueVideo(
  dialogueId: number,
  engine: 'ffmpeg' | 'remotion' = 'ffmpeg',
): Promise<VideoExportJob> {
  const response = await fetch(
    `${API_BASE}/learner/dialogues/${dialogueId}/export-video`,
    {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ engine }),
    },
  )
  if (!response.ok) {
    throw new Error(`Video export failed (${response.status})`)
  }
  return (await response.json()) as VideoExportJob
}
