import React from 'react'
import { Composition } from 'remotion'
import {
  KaraokeComposition,
  type KaraokeCompositionProps,
} from './KaraokeComposition'

export const RemotionRoot: React.FC = () => {
  return (
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
  )
}
