import React from 'react'
import { AbsoluteFill, Html5Audio, Sequence, useCurrentFrame } from 'remotion'

export type KaraokeLine = {
  speaker: string
  text: string
  audioPath?: string
  audioUrl?: string
  timestamps?: { word: string; offset_ms: number; duration_ms: number }[]
}

export type KaraokeCompositionProps = {
  title: string
  lines: KaraokeLine[]
}

const FRAMES_PER_LINE = 90

export const KaraokeComposition: React.FC<KaraokeCompositionProps> = ({
  title,
  lines,
}) => {
  const frame = useCurrentFrame()
  const active = Math.min(
    Math.floor(frame / FRAMES_PER_LINE),
    Math.max(lines.length - 1, 0),
  )
  const line = lines[active]

  return (
    <AbsoluteFill
      style={{
        backgroundColor: '#0f172a',
        color: 'white',
        fontFamily: 'Georgia, serif',
        padding: 80,
      }}
    >
      <div style={{ fontSize: 42, opacity: 0.85 }}>{title}</div>
      {lines.map((item, index) => (
        <Sequence
          key={`${item.speaker}-${index}`}
          from={index * FRAMES_PER_LINE}
          durationInFrames={FRAMES_PER_LINE}
        >
          <AbsoluteFill
            style={{
              justifyContent: 'center',
              padding: 80,
            }}
          >
            {item.audioUrl || item.audioPath ? (
              <Html5Audio src={item.audioUrl || item.audioPath} />
            ) : null}
            <div style={{ fontSize: 28, color: '#5eead4', marginBottom: 16 }}>
              {item.speaker}
            </div>
            <div style={{ fontSize: 48, lineHeight: 1.35 }}>{item.text}</div>
          </AbsoluteFill>
        </Sequence>
      ))}
      {!line ? (
        <div style={{ marginTop: 120, fontSize: 36 }}>No lines</div>
      ) : null}
    </AbsoluteFill>
  )
}
