import React from 'react'
import { Composition } from 'remotion'
import {
  DualTalkComposition,
  type DualTalkCompositionProps,
} from './DualTalkComposition'
import {
  KaraokeComposition,
  type KaraokeCompositionProps,
} from './KaraokeComposition'

export const RemotionRoot: React.FC = () => {
  return (
    <>
      <Composition
        id="Karaoke"
        component={KaraokeComposition}
        durationInFrames={300}
        fps={30}
        width={1920}
        height={1080}
        defaultProps={
          {
            title: 'LearnEnglish',
            lines: [],
          } satisfies KaraokeCompositionProps
        }
        calculateMetadata={async ({ props }) => {
          const lineCount = Math.max(props.lines?.length ?? 1, 1)
          return {
            durationInFrames: Math.max(lineCount * 90, 90),
          }
        }}
      />
      <Composition
        id="DualTalk"
        component={DualTalkComposition}
        durationInFrames={300}
        fps={30}
        width={1920}
        height={1080}
        defaultProps={
          {
            title: 'LearnEnglish',
            isbn: '',
            edition: '',
            durationMs: 10_000,
            speakers: [],
            lines: [],
          } satisfies DualTalkCompositionProps
        }
        calculateMetadata={async ({ props }) => {
          const fps = props.fps ?? 30
          const durationMs = props.durationMs ?? 10_000
          const lineCount = Math.max(props.lines?.length ?? 1, 1)
          const fromLines = lineCount * 90
          const fromAudio = Math.ceil((durationMs / 1000) * fps)
          return {
            durationInFrames: Math.max(fromAudio, fromLines, fps),
          }
        }}
      />
    </>
  )
}
