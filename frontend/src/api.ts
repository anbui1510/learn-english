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
