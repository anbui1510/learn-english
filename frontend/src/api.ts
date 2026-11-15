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

export async function generateDialogues(
  caseId: number,
): Promise<{ ok: true } | { status: number; detail: string }> {
  const response = await fetch(
    `${API_BASE}/editor/cases/${caseId}/generate-dialogues`,
    {
      method: 'POST',
      credentials: 'include',
    },
  )
  if (response.ok) {
    return { ok: true }
  }
  const detail = await response.text()
  return { status: response.status, detail }
}
