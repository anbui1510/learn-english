import { useCallback, useEffect, useState } from 'react'
import { AdminUsers } from './AdminUsers'
import { EditorFacts } from './EditorFacts'
import { EditorUpload } from './EditorUpload'
import { LearnerPanel } from './LearnerPanel'
import { fetchMe, loginUrl, logout, type AuthUser } from './api'

function App() {
  const [user, setUser] = useState<AuthUser | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const handleError = useCallback((message: string | null) => {
    setError(message)
  }, [])

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const me = await fetchMe()
        if (!cancelled) {
          setUser(me)
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Could not load session')
        }
      } finally {
        if (!cancelled) {
          setLoading(false)
        }
      }
    })()
    return () => {
      cancelled = true
    }
  }, [])

  async function onLogout() {
    setError(null)
    try {
      await logout()
      setUser(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Logout failed')
    }
  }

  return (
    <main className="min-h-screen bg-slate-50 text-slate-900">
      <div className="mx-auto flex max-w-3xl flex-col gap-4 px-6 py-16">
        <p className="text-sm font-medium tracking-wide text-teal-700">
          LearnEnglish
        </p>
        <h1 className="text-3xl font-semibold tracking-tight">
          Medical English practice
        </h1>
        <p className="max-w-prose text-slate-600">
          Sign in with Google. Editors publish Nelson cases; learners practice karaoke and shadowing.
        </p>

        <div className="flex flex-wrap items-center gap-3 pt-2">
          {loading ? (
            <p className="text-sm text-slate-500">Checking session…</p>
          ) : user ? (
            <>
              <p className="text-sm text-slate-700">
                Signed in as{' '}
                <span className="font-medium">{user.email}</span>
                <span className="text-slate-500"> ({user.role})</span>
              </p>
              <button
                type="button"
                onClick={() => void onLogout()}
                className="rounded-md bg-slate-900 px-3 py-2 text-sm font-medium text-white hover:bg-slate-800"
              >
                Log out
              </button>
            </>
          ) : (
            <a
              href={loginUrl()}
              className="rounded-md bg-teal-700 px-3 py-2 text-sm font-medium text-white hover:bg-teal-600"
            >
              Sign in with Google
            </a>
          )}
        </div>

        {error ? (
          <p className="text-sm text-red-700" role="alert">
            {error}
          </p>
        ) : null}

        {user?.role === 'admin' ? <AdminUsers onError={handleError} /> : null}
        {user?.role === 'editor' || user?.role === 'admin' ? (
          <>
            <EditorUpload onError={handleError} />
            <EditorFacts onError={handleError} />
          </>
        ) : null}
        {user ? <LearnerPanel onError={handleError} /> : null}
      </div>
    </main>
  )
}

export default App
