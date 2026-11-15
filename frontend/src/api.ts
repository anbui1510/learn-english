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

export function loginUrl(): string {
  return `${API_BASE}/auth/google/login`
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
  pdf_object_key: string | null
  pdf_byte_size: number | null
  extract_status: ExtractStatus
  extract_error: string | null
  published_at: string | null
  published_by_user_id: number | null
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
}): Promise<CaseDraft> {
  const body = new FormData()
  body.set('title', input.title)
  body.set('isbn', input.isbn)
  body.set('edition', input.edition)
  body.set('file', input.file)
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

export async function generateDialogues(
  caseId: number,
  input: {
    contexts: DialogueContext[]
    cefr_level: CefrLevel
    include_vi?: boolean
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
  const response = await fetch(
    `${API_BASE}/learner/dialogues/${dialogueId}/lesson`,
    { credentials: 'include' },
  )
  if (!response.ok) {
    throw new Error(`Failed to load lesson (${response.status})`)
  }
  return (await response.json()) as Lesson
}

export async function fetchShadowing(
  dialogueId: number,
): Promise<ShadowingCard[]> {
  const response = await fetch(
    `${API_BASE}/learner/dialogues/${dialogueId}/shadowing`,
    { credentials: 'include' },
  )
  if (!response.ok) {
    throw new Error(`Failed to load shadowing (${response.status})`)
  }
  const body = (await response.json()) as { cards: ShadowingCard[] }
  return body.cards
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

export async function completeLesson(dialogueId: number): Promise<void> {
  const response = await fetch(`${API_BASE}/learner/completions`, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ dialogue_id: dialogueId }),
  })
  if (!response.ok) {
    throw new Error(`Failed to complete lesson (${response.status})`)
  }
}

export async function uploadAttemptAudio(input: {
  dialogueId: number
  mode: 'shadowing' | 'role_play'
  file: Blob
}): Promise<void> {
  const body = new FormData()
  body.set('dialogue_id', String(input.dialogueId))
  body.set('mode', input.mode)
  body.set('file', input.file, 'attempt.webm')
  const response = await fetch(`${API_BASE}/learner/attempts/audio`, {
    method: 'POST',
    credentials: 'include',
    body,
  })
  if (!response.ok) {
    throw new Error(`Attempt upload failed (${response.status})`)
  }
}
