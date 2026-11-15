import type { Lesson, ShadowingCard } from './api'

const META_DB = 'learnenglish-offline'
const META_STORE = 'dialogues'
const AUDIO_CACHE = 'learnenglish-audio-v1'
const MAX_DIALOGUES = 3

export type CachedDialogue = {
  dialogueId: number
  lesson: Lesson
  shadowing: ShadowingCard[]
  cachedAt: number
}

function openDb(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(META_DB, 1)
    req.onupgradeneeded = () => {
      const db = req.result
      if (!db.objectStoreNames.contains(META_STORE)) {
        db.createObjectStore(META_STORE, { keyPath: 'dialogueId' })
      }
    }
    req.onsuccess = () => resolve(req.result)
    req.onerror = () => reject(req.error ?? new Error('IndexedDB open failed'))
  })
}

async function idbPut(record: CachedDialogue): Promise<void> {
  const db = await openDb()
  await new Promise<void>((resolve, reject) => {
    const tx = db.transaction(META_STORE, 'readwrite')
    tx.objectStore(META_STORE).put(record)
    tx.oncomplete = () => resolve()
    tx.onerror = () => reject(tx.error ?? new Error('IndexedDB put failed'))
  })
  db.close()
}

async function idbGet(dialogueId: number): Promise<CachedDialogue | null> {
  const db = await openDb()
  const record = await new Promise<CachedDialogue | null>((resolve, reject) => {
    const tx = db.transaction(META_STORE, 'readonly')
    const req = tx.objectStore(META_STORE).get(dialogueId)
    req.onsuccess = () => resolve((req.result as CachedDialogue | undefined) ?? null)
    req.onerror = () => reject(req.error ?? new Error('IndexedDB get failed'))
  })
  db.close()
  return record
}

async function idbList(): Promise<CachedDialogue[]> {
  const db = await openDb()
  const rows = await new Promise<CachedDialogue[]>((resolve, reject) => {
    const tx = db.transaction(META_STORE, 'readonly')
    const req = tx.objectStore(META_STORE).getAll()
    req.onsuccess = () => resolve((req.result as CachedDialogue[]) ?? [])
    req.onerror = () => reject(req.error ?? new Error('IndexedDB list failed'))
  })
  db.close()
  return rows
}

async function idbDelete(dialogueId: number): Promise<void> {
  const db = await openDb()
  await new Promise<void>((resolve, reject) => {
    const tx = db.transaction(META_STORE, 'readwrite')
    tx.objectStore(META_STORE).delete(dialogueId)
    tx.oncomplete = () => resolve()
    tx.onerror = () => reject(tx.error ?? new Error('IndexedDB delete failed'))
  })
  db.close()
}

function audioRequest(dialogueId: number, lineIndex: number): Request {
  return new Request(`https://learnenglish.local/offline-audio/${dialogueId}/${lineIndex}`)
}

async function cachePlaylistAudio(lesson: Lesson): Promise<void> {
  if (typeof caches === 'undefined') return
  const cache = await caches.open(AUDIO_CACHE)
  await Promise.all(
    lesson.playlist.map(async (item, lineIndex) => {
      if (!item.audio_url) return
      try {
        const response = await fetch(item.audio_url)
        if (!response.ok) return
        await cache.put(audioRequest(lesson.dialogue_id, lineIndex), response.clone())
      } catch {
        // Skip individual line failures; lesson JSON still useful offline.
      }
    }),
  )
}

async function enforceLru(keepId: number): Promise<void> {
  const rows = await idbList()
  if (rows.length <= MAX_DIALOGUES) return
  const sorted = [...rows].sort((a, b) => b.cachedAt - a.cachedAt)
  const drop = sorted.slice(MAX_DIALOGUES).filter((r) => r.dialogueId !== keepId)
  if (typeof caches !== 'undefined') {
    const cache = await caches.open(AUDIO_CACHE)
    for (const row of drop) {
      await idbDelete(row.dialogueId)
      for (let i = 0; i < row.lesson.playlist.length; i += 1) {
        await cache.delete(audioRequest(row.dialogueId, i))
      }
    }
  } else {
    for (const row of drop) {
      await idbDelete(row.dialogueId)
    }
  }
}

/** Persist lesson + shadowing and prefetch line audio into Cache API. */
export async function cacheDialogueOffline(
  dialogueId: number,
  lesson: Lesson,
  shadowing: ShadowingCard[],
): Promise<void> {
  if (typeof indexedDB === 'undefined') return
  await idbPut({
    dialogueId,
    lesson,
    shadowing,
    cachedAt: Date.now(),
  })
  await cachePlaylistAudio(lesson)
  await enforceLru(dialogueId)
}

export async function readCachedDialogue(
  dialogueId: number,
): Promise<CachedDialogue | null> {
  if (typeof indexedDB === 'undefined') return null
  try {
    return await idbGet(dialogueId)
  } catch {
    return null
  }
}

/**
 * Prefer a cached audio blob URL when available (offline / expired signed URL).
 * Falls back to the network `signedUrl`.
 */
export async function resolveLessonAudioUrl(
  dialogueId: number,
  lineIndex: number,
  signedUrl: string,
): Promise<string> {
  if (typeof caches === 'undefined') return signedUrl
  try {
    const cache = await caches.open(AUDIO_CACHE)
    const hit = await cache.match(audioRequest(dialogueId, lineIndex))
    if (hit) {
      const blob = await hit.blob()
      return URL.createObjectURL(blob)
    }
  } catch {
    // ignore
  }
  return signedUrl
}

export function isBrowserOffline(): boolean {
  return typeof navigator !== 'undefined' && navigator.onLine === false
}
