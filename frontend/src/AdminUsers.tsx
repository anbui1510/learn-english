import { useEffect, useState } from 'react'
import {
  assignRole,
  createBookSource,
  fetchPaUsage,
  fetchTtsSettings,
  listAdminBookSources,
  listUsers,
  patchTtsSettings,
  type AdminUser,
  type BookSource,
  type PaUsageRow,
  type Role,
  type TtsProvider,
  type TtsSettings,
} from './api'

const ROLE_OPTIONS: Role[] = ['learner', 'editor', 'admin']

type Props = {
  onError: (message: string | null) => void
}

export function AdminUsers({ onError }: Props) {
  const [users, setUsers] = useState<AdminUser[]>([])
  const [paUsage, setPaUsage] = useState<PaUsageRow[]>([])
  const [bookSources, setBookSources] = useState<BookSource[]>([])
  const [tts, setTts] = useState<TtsSettings | null>(null)
  const [newSlug, setNewSlug] = useState('')
  const [newTitle, setNewTitle] = useState('')
  const [loading, setLoading] = useState(true)
  const [savingId, setSavingId] = useState<number | null>(null)

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const [rows, usage, sources, ttsSettings] = await Promise.all([
          listUsers(),
          fetchPaUsage(14),
          listAdminBookSources(),
          fetchTtsSettings(),
        ])
        if (!cancelled) {
          setUsers(rows)
          setPaUsage(usage)
          setBookSources(sources)
          setTts(ttsSettings)
          onError(null)
        }
      } catch (err) {
        if (!cancelled) {
          onError(err instanceof Error ? err.message : 'Failed to load users')
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
  }, [onError])

  async function onRoleChange(userId: number, role: Role) {
    setSavingId(userId)
    onError(null)
    try {
      const updated = await assignRole(userId, role)
      setUsers((prev) => prev.map((u) => (u.id === userId ? updated : u)))
    } catch (err) {
      onError(err instanceof Error ? err.message : 'Failed to assign role')
    } finally {
      setSavingId(null)
    }
  }

  const paTotalCost = paUsage.reduce((sum, row) => sum + row.estimated_cost_usd, 0)

  return (
    <section className="mt-8 border-t border-slate-200 pt-8">
      <h2 className="text-xl font-semibold tracking-tight">User roles</h2>
      <p className="mt-1 text-sm text-slate-600">
        Assign editor or learner. Editors are normal accounts with the editor
        role — not admins.
      </p>

      {loading ? (
        <p className="mt-4 text-sm text-slate-500">Loading users…</p>
      ) : (
        <div className="mt-4 overflow-x-auto">
          <table className="w-full min-w-[28rem] text-left text-sm">
            <thead>
              <tr className="border-b border-slate-200 text-slate-500">
                <th className="py-2 pr-4 font-medium">Email</th>
                <th className="py-2 pr-4 font-medium">Name</th>
                <th className="py-2 font-medium">Role</th>
              </tr>
            </thead>
            <tbody>
              {users.map((user) => (
                <tr key={user.id} className="border-b border-slate-100">
                  <td className="py-2 pr-4">{user.email}</td>
                  <td className="py-2 pr-4 text-slate-600">
                    {user.name ?? '—'}
                  </td>
                  <td className="py-2">
                    <select
                      className="rounded border border-slate-300 bg-white px-2 py-1"
                      value={user.role}
                      disabled={savingId === user.id}
                      onChange={(event) =>
                        void onRoleChange(user.id, event.target.value as Role)
                      }
                    >
                      {ROLE_OPTIONS.map((role) => (
                        <option key={role} value={role}>
                          {role}
                        </option>
                      ))}
                    </select>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div className="mt-8">
        <h3 className="text-base font-semibold">TTS provider</h3>
        <p className="mt-1 text-sm text-slate-500">
          Org voice engine + premium cost gate (Azure / ElevenLabs need keys in
          env).
        </p>
        {tts ? (
          <div className="mt-2 flex flex-wrap items-end gap-3 text-sm">
            <label>
              Provider
              <select
                className="mt-1 block rounded border border-slate-300 px-2 py-1"
                value={tts.provider}
                onChange={(e) => {
                  const provider = e.target.value as TtsProvider
                  void (async () => {
                    try {
                      onError(null)
                      setTts(await patchTtsSettings({ provider }))
                    } catch (err) {
                      onError(
                        err instanceof Error
                          ? err.message
                          : 'Failed to update TTS',
                      )
                    }
                  })()
                }}
              >
                <option value="synthetic">synthetic (CI)</option>
                <option value="edge">edge-tts</option>
                <option value="azure">Azure Neural</option>
                <option value="elevenlabs">ElevenLabs</option>
              </select>
            </label>
            <label className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={tts.premium_enabled}
                onChange={(e) => {
                  const premium_enabled = e.target.checked
                  void (async () => {
                    try {
                      onError(null)
                      setTts(await patchTtsSettings({ premium_enabled }))
                    } catch (err) {
                      onError(
                        err instanceof Error
                          ? err.message
                          : 'Failed to update TTS',
                      )
                    }
                  })()
                }}
              />
              Premium enabled (cost flag)
            </label>
          </div>
        ) : null}
      </div>

      <div className="mt-8">
        <h3 className="text-base font-semibold">Book sources</h3>
        <p className="mt-1 text-sm text-slate-500">
          Nelson, Harriet Lane, WHO, and custom guideline libraries.
        </p>
        <ul className="mt-2 space-y-1 text-sm">
          {bookSources.map((source) => (
            <li key={source.id}>
              <span className="font-medium">{source.title}</span>
              <span className="text-slate-500"> ({source.slug})</span>
              {source.default_isbn ? (
                <span className="text-slate-500"> · ISBN {source.default_isbn}</span>
              ) : null}
            </li>
          ))}
        </ul>
        <form
          className="mt-3 flex flex-wrap items-end gap-2 text-sm"
          onSubmit={(e) => {
            e.preventDefault()
            void (async () => {
              try {
                onError(null)
                const created = await createBookSource({
                  slug: newSlug,
                  title: newTitle,
                })
                setBookSources((prev) =>
                  [...prev, created].sort((a, b) =>
                    a.title.localeCompare(b.title),
                  ),
                )
                setNewSlug('')
                setNewTitle('')
              } catch (err) {
                onError(
                  err instanceof Error
                    ? err.message
                    : 'Failed to create book source',
                )
              }
            })()
          }}
        >
          <label>
            Slug
            <input
              className="mt-1 block rounded border border-slate-300 px-2 py-1"
              value={newSlug}
              onChange={(e) => setNewSlug(e.target.value)}
              required
            />
          </label>
          <label>
            Title
            <input
              className="mt-1 block rounded border border-slate-300 px-2 py-1"
              value={newTitle}
              onChange={(e) => setNewTitle(e.target.value)}
              required
            />
          </label>
          <button
            type="submit"
            className="rounded-md border border-slate-300 px-3 py-1.5 font-medium"
          >
            Add source
          </button>
        </form>
      </div>

      <div className="mt-8">
        <h3 className="text-base font-semibold">PA usage (14 days)</h3>
        <p className="mt-1 text-sm text-slate-500">
          Score calls per user/day for Azure cost control. Est. total $
          {paTotalCost.toFixed(4)}
        </p>
        {paUsage.length === 0 ? (
          <p className="mt-2 text-sm text-slate-500">No PA usage yet.</p>
        ) : (
          <ul className="mt-2 space-y-1 text-sm">
            {paUsage.slice(0, 20).map((row) => (
              <li key={`${row.user_id}-${row.usage_day}`}>
                {row.usage_day} · {row.email ?? `user #${row.user_id}`} ·{' '}
                {row.score_count} scores · ${row.estimated_cost_usd.toFixed(4)}
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  )
}
