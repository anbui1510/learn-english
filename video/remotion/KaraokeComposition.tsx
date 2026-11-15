/**
 * Remotion composition stub — not built in CI.
 * Replace the ffmpeg exporter when Remotion deps are installed.
 */
export type KaraokeLine = {
  speaker: string
  text: string
  audioUrl: string
  timestamps: { word: string; offset_ms: number; duration_ms: number }[]
}

export type KaraokeCompositionProps = {
  title: string
  lines: KaraokeLine[]
}

export function KaraokeComposition(_props: KaraokeCompositionProps) {
  return null
}
