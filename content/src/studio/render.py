from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Protocol

from studio.paths import cases_root, repo_root
from studio.review import assert_accepted
from studio.synthesize import FEMALE_SPEAKERS, _stems_for_case

REMOTION_ROOT = repo_root() / "video" / "remotion"
FPS = 30
WIDTH = 1920
HEIGHT = 1080


class RemotionRenderer(Protocol):
    def render(
        self,
        *,
        props_path: Path,
        output_path: Path,
        width: int,
        height: int,
    ) -> None: ...


class CliRemotionRenderer:
    """Invoke Remotion CLI for the DualTalk composition."""

    def render(
        self,
        *,
        props_path: Path,
        output_path: Path,
        width: int,
        height: int,
    ) -> None:
        if not (REMOTION_ROOT / "package.json").is_file():
            raise RuntimeError("Remotion package missing under video/remotion")
        cmd = [
            "npx",
            "--yes",
            "remotion",
            "render",
            "src/index.ts",
            "DualTalk",
            str(output_path),
            f"--props={props_path}",
            f"--width={width}",
            f"--height={height}",
        ]
        proc = subprocess.run(
            cmd,
            cwd=str(REMOTION_ROOT),
            capture_output=True,
            check=False,
        )
        if proc.returncode != 0 or not output_path.is_file():
            raise RuntimeError(
                proc.stderr.decode("utf-8", errors="ignore")[-500:]
                or "Remotion render failed"
            )


def _default_remotion_renderer() -> RemotionRenderer:
    return CliRemotionRenderer()


def _case_dir(case_id: str) -> Path:
    case_dir = cases_root() / case_id
    if not case_dir.is_dir():
        raise FileNotFoundError(f"Case not found: {case_id}")
    return case_dir


def _load_case_meta(case_dir: Path) -> dict[str, object]:
    path = case_dir / "case.json"
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _load_dialogue(case_dir: Path, stem: str) -> dict[str, object]:
    path = case_dir / "dialogues" / f"{stem}.json"
    if not path.is_file():
        raise FileNotFoundError(f"Dialogue not found: {stem}")
    return json.loads(path.read_text(encoding="utf-8"))


def _speaker_label(speaker: str) -> str:
    return speaker.replace("_", " ").strip().title() or "Speaker"


def _avatar_for_speaker(speaker: str) -> str:
    """Map speaker role → Remotion public/ avatar (real portraits, not 8×8 stubs)."""
    key = speaker.strip().lower()
    role_avatars = {
        "doctor": "avatars/doctor.jpg",
        "expert": "avatars/expert.jpg",
        "colleague": "avatars/colleague.jpg",
        "learner": "avatars/colleague.jpg",
        "parent": "avatars/parent.jpg",
        "mother": "avatars/parent.jpg",
        "family": "avatars/parent.jpg",
        "nurse": "avatars/parent.jpg",
        "jenny": "avatars/parent.jpg",
    }
    if key in role_avatars:
        return role_avatars[key]
    if key in FEMALE_SPEAKERS:
        return "avatars/parent.jpg"
    return "avatars/doctor.jpg"


def build_dualtalk_props(case_dir: Path, stem: str) -> dict[str, object]:
    """Build Remotion DualTalk props from case audio + dialogue artifacts."""
    case_meta = _load_case_meta(case_dir)
    dialogue = _load_dialogue(case_dir, stem)
    ts_path = case_dir / "audio" / stem / "timestamps.json"
    if not ts_path.is_file():
        raise FileNotFoundError(
            f"Missing timestamps for {stem}; run synthesize first"
        )
    timestamps = json.loads(ts_path.read_text(encoding="utf-8"))

    dialogue_lines = dialogue.get("lines") or []
    text_by_index: dict[int, dict[str, str]] = {}
    for index, line in enumerate(dialogue_lines):
        text_by_index[index] = {
            "text": str(line.get("text") or ""),
            "text_vi": str(line.get("text_vi") or ""),
        }

    lines_out: list[dict[str, object]] = []
    speaker_order: list[str] = []
    for entry in timestamps.get("lines") or []:
        line_index = int(entry.get("line_index", 0))
        speaker = str(entry.get("speaker") or "speaker").strip()
        speaker_key = speaker.lower()
        if speaker_key not in speaker_order:
            speaker_order.append(speaker_key)
        speaker = speaker_key
        copy = text_by_index.get(line_index, {})
        words = entry.get("words") or []
        lines_out.append(
            {
                "speaker": speaker,
                "text": str(entry.get("text") or copy.get("text") or ""),
                "textVi": copy.get("text_vi") or "",
                "offsetMs": int(entry.get("offset_ms") or 0),
                "durationMs": int(entry.get("duration_ms") or 0),
                "words": [
                    {
                        "word": str(w.get("word") or ""),
                        "offsetMs": int(w.get("offset_ms") or 0),
                        "durationMs": int(w.get("duration_ms") or 1),
                    }
                    for w in words
                ],
            }
        )

    speakers_out: list[dict[str, object]] = []
    for index, speaker_id in enumerate(speaker_order[:2]):
        speakers_out.append(
            {
                "id": speaker_id,
                "label": _speaker_label(speaker_id),
                "avatarUrl": _avatar_for_speaker(speaker_id),
                "side": "left" if index == 0 else "right",
            }
        )

    full_name = str(timestamps.get("full") or "full.wav")
    full_audio = case_dir / "audio" / stem / full_name
    if not full_audio.is_file():
        raise FileNotFoundError(f"Missing full audio: {full_audio}")

    # Remotion can only load media from http(s) or files under public/ via staticFile.
    # Stage a copy under video/remotion/public/studio-audio/<case>/<stem>.<ext>.
    case_id = case_dir.name
    ext = full_audio.suffix.lstrip(".") or "mp3"
    public_rel = f"studio-audio/{case_id}/{stem}.{ext}"
    staged = REMOTION_ROOT / "public" / public_rel
    staged.parent.mkdir(parents=True, exist_ok=True)
    if not staged.is_file() or staged.stat().st_mtime < full_audio.stat().st_mtime:
        shutil.copy2(full_audio, staged)

    duration_ms = int(timestamps.get("duration_ms") or 0)
    if duration_ms <= 0 and lines_out:
        last = lines_out[-1]
        duration_ms = int(last["offsetMs"]) + int(last["durationMs"])

    return {
        "title": str(case_meta.get("title") or stem),
        "isbn": str(case_meta.get("isbn") or ""),
        "edition": str(case_meta.get("edition") or ""),
        "fps": FPS,
        "durationMs": max(duration_ms, 1000),
        # Remotion reads staged public/ path; ffmpeg fallback uses absolute case audio.
        "fullAudioPath": public_rel,
        "sourceAudioPath": str(full_audio.resolve()),
        "speakers": speakers_out,
        "lines": lines_out,
    }


def _write_props(case_dir: Path, stem: str, props: dict[str, object]) -> Path:
    video_dir = case_dir / "video"
    video_dir.mkdir(parents=True, exist_ok=True)
    path = video_dir / f"{stem}.props.json"
    path.write_text(json.dumps(props, indent=2) + "\n", encoding="utf-8")
    return path


def _write_render_meta(
    case_dir: Path, stem: str, *, engine: str, output: Path
) -> Path:
    video_dir = case_dir / "video"
    path = video_dir / f"{stem}.render.json"
    payload = {
        "dialogue_stem": stem,
        "engine": engine,
        "output": output.name,
        "path": str(output),
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def _escape_drawtext(value: str) -> str:
    cleaned = value.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")
    cleaned = cleaned.replace("%", "\\%")
    return cleaned[:120]


def _build_srt(lines: list[dict[str, object]], *, duration_ms: int) -> str:
    chunks: list[str] = []
    for index, line in enumerate(lines, start=1):
        start_ms = int(line.get("offsetMs") or 0)
        end_ms = start_ms + int(line.get("durationMs") or 0)
        if index == len(lines):
            end_ms = max(end_ms, duration_ms)
        speaker = str(line.get("speaker") or "")
        text = str(line.get("text") or "")
        chunks.append(str(index))
        chunks.append(f"{_srt_time(start_ms)} --> {_srt_time(end_ms)}")
        chunks.append(f"{_speaker_label(speaker)}: {text}")
        chunks.append("")
    return "\n".join(chunks) + "\n"


def _srt_time(ms: int) -> str:
    ms = max(0, ms)
    hours = ms // 3_600_000
    ms -= hours * 3_600_000
    minutes = ms // 60_000
    ms -= minutes * 60_000
    seconds = ms // 1000
    millis = ms % 1000
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{millis:03d}"


def _ffmpeg_render_dualtalk(
    *,
    output_path: Path,
    props: dict[str, object],
    audio_path: Path,
) -> None:
    if shutil.which("ffmpeg") is None:
        raise RuntimeError("ffmpeg is not installed")
    lines = list(props.get("lines") or [])
    if not lines:
        raise ValueError("No dialogue lines for ffmpeg render")
    duration_ms = int(props.get("durationMs") or 1000)
    duration_s = max(duration_ms / 1000.0, 1.0)
    title = _escape_drawtext(str(props.get("title") or "Dialogue"))
    isbn = str(props.get("isbn") or "")
    edition = str(props.get("edition") or "")
    footer_bits = [title]
    if isbn:
        footer_bits.append(f"ISBN {isbn}")
    if edition:
        footer_bits.append(f"ed. {edition}")
    footer = _escape_drawtext(" · ".join(footer_bits))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        srt_path = work / "captions.srt"
        srt_path.write_text(_build_srt(lines, duration_ms=duration_ms), encoding="utf-8")

        # Single-scene video: full audio + burnt-in subtitles + title/footer.
        vf_parts = [
            f"subtitles={srt_path}:force_style='FontSize=28,PrimaryColour=&Hffffff,OutlineColour=&H000000,BorderStyle=3'",
            f"drawtext=fontcolor=white:fontsize=36:x=(w-text_w)/2:y=60:text='{title}'",
            f"drawtext=fontcolor=0x94a3b8:fontsize=22:x=(w-text_w)/2:y=h-48:text='{footer}'",
        ]
        cmd = [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"color=c=0x0f172a:s={WIDTH}x{HEIGHT}:d={duration_s:.3f}",
            "-i",
            str(audio_path),
            "-shortest",
            "-vf",
            ",".join(vf_parts),
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            str(output_path),
        ]
        proc = subprocess.run(cmd, capture_output=True, check=False)
        if proc.returncode != 0:
            cmd_plain = [
                "ffmpeg",
                "-y",
                "-f",
                "lavfi",
                "-i",
                f"color=c=0x0f172a:s={WIDTH}x{HEIGHT}:d={duration_s:.3f}",
                "-i",
                str(audio_path),
                "-shortest",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                "-b:a",
                "128k",
                str(output_path),
            ]
            proc2 = subprocess.run(cmd_plain, capture_output=True, check=False)
            if proc2.returncode != 0 or not output_path.is_file():
                err = proc.stderr.decode("utf-8", errors="ignore")[-500:]
                err2 = proc2.stderr.decode("utf-8", errors="ignore")[-500:]
                raise RuntimeError(err or err2 or "ffmpeg render failed")


def render_dialogue(
    case_id: str,
    stem: str,
    *,
    force: bool = False,
    remotion: RemotionRenderer | None = None,
) -> Path:
    """Render DualTalk MP4 via Remotion, falling back to ffmpeg when needed."""
    assert_accepted(case_id, stem, force=force)
    case_dir = _case_dir(case_id)
    props = build_dualtalk_props(case_dir, stem)
    props_path = _write_props(case_dir, stem, props)
    output_path = case_dir / "video" / f"{stem}.mp4"

    renderer = remotion or _default_remotion_renderer()
    engine = "ffmpeg"
    try:
        renderer.render(
            props_path=props_path,
            output_path=output_path,
            width=WIDTH,
            height=HEIGHT,
        )
        if output_path.is_file() and output_path.stat().st_size > 0:
            engine = "remotion"
    except Exception:
        audio_path = Path(
            str(props.get("sourceAudioPath") or props.get("fullAudioPath") or "")
        )
        _ffmpeg_render_dualtalk(
            output_path=output_path,
            props=props,
            audio_path=audio_path,
        )

    if not output_path.is_file() or output_path.stat().st_size == 0:
        raise RuntimeError(f"Render produced no output for {stem}")

    _write_render_meta(case_dir, stem, engine=engine, output=output_path)
    return output_path


def render_case(
    case_id: str,
    dialogue_stem: str | None = None,
    *,
    force: bool = False,
) -> list[Path]:
    """Render video for one or all accepted dialogues with synthesized audio."""
    case_dir = _case_dir(case_id)
    stems = _stems_for_case(case_id, dialogue_stem)
    if not stems:
        raise ValueError(
            f"No dialogues to render for case {case_id}"
            + (f" (stem={dialogue_stem!r})" if dialogue_stem else "")
        )
    written: list[Path] = []
    for stem in stems:
        ts_path = case_dir / "audio" / stem / "timestamps.json"
        if not ts_path.is_file():
            raise FileNotFoundError(
                f"Missing audio for {stem}; synthesize before render"
            )
        written.append(render_dialogue(case_id, stem, force=force))
    return written