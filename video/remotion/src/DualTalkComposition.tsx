import React from 'react'
import {
  AbsoluteFill,
  Audio,
  Img,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from 'remotion'

export type DualTalkWord = {
  word: string
  offsetMs: number
  durationMs: number
}

export type DualTalkLine = {
  speaker: string
  text: string
  textVi?: string
  offsetMs: number
  durationMs: number
  words?: DualTalkWord[]
}

export type DualTalkSpeaker = {
  id: string
  label: string
  avatarUrl: string
  side: 'left' | 'right'
}

export type DualTalkCompositionProps = {
  title: string
  isbn?: string
  edition?: string
  fps?: number
  durationMs: number
  fullAudioPath?: string
  speakers: DualTalkSpeaker[]
  lines: DualTalkLine[]
}

const PANEL_ACTIVE = 'rgba(94, 234, 212, 0.22)'
const PANEL_IDLE = 'rgba(15, 23, 42, 0.92)'
const BORDER_ACTIVE = '#5eead4'
const BORDER_IDLE = '#334155'

function msToFrame(ms: number, fps: number): number {
  return Math.floor((ms / 1000) * fps)
}

function activeLineIndex(lines: DualTalkLine[], frame: number, fps: number): number {
  if (!lines.length) {
    return 0
  }
  const timeMs = (frame / fps) * 1000
  let index = 0
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i]
    const start = line.offsetMs
    const end = line.offsetMs + line.durationMs
    if (timeMs >= start && timeMs < end) {
      return i
    }
    if (timeMs >= end) {
      index = i
    }
  }
  return index
}

function CaptionWords({
  line,
  frame,
  fps,
}: {
  line: DualTalkLine
  frame: number
  fps: number
}) {
  const lineStartFrame = msToFrame(line.offsetMs, fps)
  const relativeMs = Math.max(0, ((frame - lineStartFrame) / fps) * 1000)
  const words = line.words?.length
    ? line.words
    : [{ word: line.text, offsetMs: 0, durationMs: line.durationMs }]

  return (
    <div style={{ fontSize: 44, lineHeight: 1.4, textAlign: 'center', maxWidth: 1500 }}>
      {words.map((word, index) => {
        const active =
          relativeMs >= word.offsetMs &&
          relativeMs < word.offsetMs + word.durationMs
        return (
          <span
            key={`${word.word}-${index}`}
            style={{
              color: active ? '#fbbf24' : 'white',
              fontWeight: active ? 700 : 400,
              marginRight: 10,
            }}
          >
            {word.word}
          </span>
        )
      })}
    </div>
  )
}

function SpeakerPanel({
  speaker,
  isActive,
}: {
  speaker: DualTalkSpeaker
  isActive: boolean
}) {
  return (
    <div
      style={{
        flex: 1,
        borderRadius: 24,
        border: `3px solid ${isActive ? BORDER_ACTIVE : BORDER_IDLE}`,
        backgroundColor: isActive ? PANEL_ACTIVE : PANEL_IDLE,
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        opacity: isActive ? 1 : 0.55,
        padding: 24,
      }}
    >
      <Img
        src={staticFile(speaker.avatarUrl)}
        style={{
          width: 220,
          height: 220,
          borderRadius: '50%',
          objectFit: 'cover',
          marginBottom: 24,
          border: `4px solid ${isActive ? BORDER_ACTIVE : BORDER_IDLE}`,
        }}
      />
      <div style={{ fontSize: 36, fontWeight: 700 }}>{speaker.label}</div>
    </div>
  )
}

export const DualTalkComposition: React.FC<DualTalkCompositionProps> = ({
  title,
  isbn = '',
  edition = '',
  fullAudioPath,
  speakers,
  lines,
}) => {
  const frame = useCurrentFrame()
  const { fps } = useVideoConfig()
  const activeIndex = activeLineIndex(lines, frame, fps)
  const activeLine = lines[activeIndex]
  const activeSpeaker = activeLine?.speaker

  const left = speakers.find((s) => s.side === 'left') ?? speakers[0]
  const right = speakers.find((s) => s.side === 'right') ?? speakers[1]

  const footerParts = [title]
  if (isbn) footerParts.push(`ISBN ${isbn}`)
  if (edition) footerParts.push(`ed. ${edition}`)
  const footer = footerParts.join(' · ')

  return (
    <AbsoluteFill
      style={{
        backgroundColor: '#020617',
        color: 'white',
        fontFamily: 'Georgia, serif',
      }}
    >
      {fullAudioPath ? <Audio src={fullAudioPath} /> : null}

      <AbsoluteFill style={{ flexDirection: 'row', padding: 48, gap: 32 }}>
        {left ? (
          <SpeakerPanel speaker={left} isActive={left.id === activeSpeaker} />
        ) : null}
        {right ? (
          <SpeakerPanel
            speaker={right}
            isActive={right.id === activeSpeaker}
          />
        ) : null}
      </AbsoluteFill>

      <AbsoluteFill
        style={{
          justifyContent: 'flex-end',
          alignItems: 'center',
          paddingBottom: 160,
          paddingLeft: 80,
          paddingRight: 80,
        }}
      >
        {activeLine ? (
          <>
            <CaptionWords line={activeLine} frame={frame} fps={fps} />
            {activeLine.textVi ? (
              <div
                style={{
                  marginTop: 20,
                  fontSize: 28,
                  color: '#94a3b8',
                  fontStyle: 'italic',
                }}
              >
                {activeLine.textVi}
              </div>
            ) : null}
          </>
        ) : (
          <div style={{ fontSize: 36, opacity: 0.7 }}>No captions</div>
        )}
      </AbsoluteFill>

      <AbsoluteFill
        style={{
          justifyContent: 'flex-end',
          alignItems: 'center',
          paddingBottom: 28,
        }}
      >
        <div style={{ fontSize: 22, color: '#64748b' }}>{footer}</div>
      </AbsoluteFill>
    </AbsoluteFill>
  )
}