import { useEffect, useState, type FormEvent } from 'react'
import {
  listEditorBookSources,
  uploadCasePdf,
  type BookSource,
  type CaseDraft,
} from './api'

type Props = {
  onError: (message: string | null) => void
}

export function EditorUpload({ onError }: Props) {
  const [title, setTitle] = useState('')
  const [isbn, setIsbn] = useState('')
  const [edition, setEdition] = useState('')
  const [bookSourceId, setBookSourceId] = useState<number | ''>('')
  const [sources, setSources] = useState<BookSource[]>([])
  const [file, setFile] = useState<File | null>(null)
  const [busy, setBusy] = useState(false)
  const [created, setCreated] = useState<CaseDraft | null>(null)

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const listed = await listEditorBookSources()
        if (!cancelled) setSources(listed)
      } catch {
        // Picker is optional; upload still works without sources.
      }
    })()
    return () => {
      cancelled = true
    }
  }, [])

  async function onSubmit(event: FormEvent) {
    event.preventDefault()
    if (!file) {
      onError('Choose a PDF file')
      return
    }
    setBusy(true)
    onError(null)
    try {
      const draft = await uploadCasePdf({
        title,
        isbn,
        edition,
        file,
        bookSourceId: bookSourceId === '' ? null : bookSourceId,
      })
      setCreated(draft)
      setTitle('')
      setIsbn('')
      setEdition('')
      setBookSourceId('')
      setFile(null)
    } catch (err) {
      onError(err instanceof Error ? err.message : 'Upload failed')
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="mt-8 border-t border-slate-200 pt-8">
      <h2 className="text-xl font-semibold tracking-tight">Upload PDF case</h2>
      <p className="mt-1 text-sm text-slate-600">
        ISBN and edition are required. Optionally tag a book source (Nelson,
        Harriet Lane, WHO…).
      </p>

      <form className="mt-4 flex flex-col gap-3" onSubmit={(e) => void onSubmit(e)}>
        <label className="text-sm">
          Title
          <input
            className="mt-1 w-full rounded border border-slate-300 px-2 py-1"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            required
          />
        </label>
        <label className="text-sm">
          Book source
          <select
            className="mt-1 w-full rounded border border-slate-300 px-2 py-1"
            value={bookSourceId === '' ? '' : String(bookSourceId)}
            onChange={(e) => {
              const value = e.target.value
              setBookSourceId(value ? Number(value) : '')
              const match = sources.find((s) => String(s.id) === value)
              if (match?.default_isbn && !isbn) {
                setIsbn(match.default_isbn)
              }
            }}
          >
            <option value="">Unspecified</option>
            {sources.map((source) => (
              <option key={source.id} value={source.id}>
                {source.title}
              </option>
            ))}
          </select>
        </label>
        <label className="text-sm">
          ISBN
          <input
            className="mt-1 w-full rounded border border-slate-300 px-2 py-1"
            value={isbn}
            onChange={(e) => setIsbn(e.target.value)}
            required
          />
        </label>
        <label className="text-sm">
          Edition
          <input
            className="mt-1 w-full rounded border border-slate-300 px-2 py-1"
            value={edition}
            onChange={(e) => setEdition(e.target.value)}
            required
          />
        </label>
        <label className="text-sm">
          PDF file
          <input
            className="mt-1 block w-full text-sm"
            type="file"
            accept="application/pdf,.pdf"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            required
          />
        </label>
        <button
          type="submit"
          disabled={busy}
          className="w-fit rounded-md bg-teal-700 px-3 py-2 text-sm font-medium text-white hover:bg-teal-600 disabled:opacity-60"
        >
          {busy ? 'Uploading…' : 'Upload case'}
        </button>
      </form>

      {created ? (
        <div className="mt-4 text-sm text-slate-700">
          <p>
            Created case <span className="font-medium">#{created.id}</span> —{' '}
            {created.title}
          </p>
          <p className="text-slate-500">
            ISBN {created.isbn} · edition {created.edition}
            {created.book_source_slug
              ? ` · source ${created.book_source_slug}`
              : ''}{' '}
            · {created.pdf_byte_size ?? 0} bytes · extract{' '}
            {created.extract_status}
          </p>
        </div>
      ) : null}
    </section>
  )
}
