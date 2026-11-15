# Remotion karaoke composition (G3)

Placeholder for a Remotion composition that reuses learner karaoke timestamps
(`playlist[].timestamps`) and line audio URLs.

The production export API today renders via **ffmpeg** (`backend/app/video/export.py`)
so CI stays dependency-light. Swap `engine` to `remotion` when this package is wired
into the export worker.

Suggested props:

- `title`
- `lines: { speaker, text, audioUrl, timestamps }[]`
- `width: 1920`, `height: 1080`
