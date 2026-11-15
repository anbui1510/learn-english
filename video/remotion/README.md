# Remotion karaoke composition (G3)

Composition id: **Karaoke** (`src/KaraokeComposition.tsx`).

## Local render

```bash
cd video/remotion
npm install
npm run studio
# or
npx remotion render src/index.ts Karaoke out/karaoke.mp4 --props=./sample-props.json
```

Backend export prefers this path when `engine=remotion` is requested
(`POST /learner/dialogues/{id}/export-video`). If Remotion/CLI is unavailable,
the job falls back to the ffmpeg karaoke composer and records `engine=ffmpeg`.

CI keeps using ffmpeg so the main workflow stays dependency-light.
