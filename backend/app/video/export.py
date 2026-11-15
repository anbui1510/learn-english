from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path
from typing import Any


def build_karaoke_mp4(
    *,
    output_path: Path,
    title: str,
    lines: list[dict[str, Any]],
    width: int = 1920,
    height: int = 1080,
) -> Path:
    """Compose a 1080p MP4 from per-line WAV clips + title card (ffmpeg).

    Remotion compositions under ``video/remotion`` can replace this renderer
    later while keeping the same export job API.
    """
    if not lines:
        raise ValueError("At least one audio line is required")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        concat_list = work / "concat.txt"
        segments: list[Path] = []
        for index, line in enumerate(lines):
            audio = Path(str(line["audio_path"]))
            if not audio.exists():
                raise FileNotFoundError(audio)
            speaker = str(line.get("speaker") or "speaker")
            text = str(line.get("text") or "").replace(":", " ").replace("'", "")
            # Escape for drawtext
            safe_title = title.replace(":", " ").replace("'", "")[:80]
            label = f"{speaker}: {text}"[:90].replace(":", " ")
            segment = work / f"seg-{index:03d}.mp4"
            cmd = [
                "ffmpeg",
                "-y",
                "-f",
                "lavfi",
                "-i",
                f"color=c=0x0f172a:s={width}x{height}:d=1",
                "-i",
                str(audio),
                "-shortest",
                "-vf",
                (
                    f"drawtext=fontcolor=white:fontsize=48:x=(w-text_w)/2:y=120:"
                    f"text='{safe_title}',"
                    f"drawtext=fontcolor=0x5eead4:fontsize=36:x=80:y=h/2:"
                    f"text='{label}'"
                ),
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                "-b:a",
                "128k",
                str(segment),
            ]
            proc = subprocess.run(cmd, capture_output=True, check=False)
            if proc.returncode != 0:
                # Fallback without drawtext fonts if fontconfig missing
                cmd_plain = [
                    "ffmpeg",
                    "-y",
                    "-f",
                    "lavfi",
                    "-i",
                    f"color=c=0x0f172a:s={width}x{height}:d=1",
                    "-i",
                    str(audio),
                    "-shortest",
                    "-c:v",
                    "libx264",
                    "-pix_fmt",
                    "yuv420p",
                    "-c:a",
                    "aac",
                    "-b:a",
                    "128k",
                    str(segment),
                ]
                proc2 = subprocess.run(cmd_plain, capture_output=True, check=False)
                if proc2.returncode != 0:
                    raise RuntimeError(
                        proc.stderr.decode("utf-8", errors="ignore")[-400:]
                        or proc2.stderr.decode("utf-8", errors="ignore")[-400:]
                    )
            segments.append(segment)

        with concat_list.open("w", encoding="utf-8") as handle:
            for seg in segments:
                handle.write(f"file '{seg}'\n")
        concat_cmd = [
            "ffmpeg",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_list),
            "-c",
            "copy",
            str(output_path),
        ]
        proc = subprocess.run(concat_cmd, capture_output=True, check=False)
        if proc.returncode != 0 or not output_path.exists():
            raise RuntimeError(
                proc.stderr.decode("utf-8", errors="ignore")[-400:]
            )
    return output_path
