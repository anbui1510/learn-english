const API_BASE =
  import.meta.env.VITE_API_BASE_URL?.replace(/\/$/, '') ??
  'http://127.0.0.1:8000'

export type AuthUser = {
  sub: string
  email: string
  name: string | null
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
