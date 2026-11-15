/** Short display name from Azure/Edge-style voice ids (e.g. en-US-JennyNeural). */
export function friendlyVoiceLabel(voice: string | null | undefined): string {
  if (!voice) return 'Unknown'
  const trimmed = voice.trim()
  if (!trimmed) return 'Unknown'
  const neural = trimmed.match(/([A-Za-z]+)Neural$/i)
  if (neural) return neural[1]
  const last = trimmed.split(/[-_]/).filter(Boolean).at(-1)
  return last || trimmed
}
