import { useEffect, useState } from 'react'
import { assignRole, listUsers, type AdminUser, type Role } from './api'

const ROLE_OPTIONS: Role[] = ['learner', 'editor', 'admin']

type Props = {
  onError: (message: string | null) => void
}

export function AdminUsers({ onError }: Props) {
  const [users, setUsers] = useState<AdminUser[]>([])
  const [loading, setLoading] = useState(true)
  const [savingId, setSavingId] = useState<number | null>(null)

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const rows = await listUsers()
        if (!cancelled) {
          setUsers(rows)
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
    </section>
  )
}
