import json
import shutil
import subprocess
import tempfile
from pathlib import Path


def combine_videos(paths, destination, ffmpeg="ffmpeg"):
    """Combine ordered clips. Transcode to normalize codecs, resolution and timestamps."""
    executable = shutil.which(ffmpeg) or (ffmpeg if Path(ffmpeg).exists() else None)
    if not executable:
        raise RuntimeError("Chưa tìm thấy FFmpeg. Hãy cài FFmpeg hoặc chọn đúng đường dẫn.")
    videos = [Path(p).resolve() for p in paths]
    if len(videos) < 2:
        raise ValueError("Cần tối thiểu 2 video để ghép.")
    for item in videos:
        if not item.is_file():
            raise FileNotFoundError(str(item))
    output = Path(destination).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    if output in videos:
        raise ValueError("Không thể ghi đè một video đầu vào.")
    # Filter concat with varying codecs is unreliable. Normalize clips separately.
    with tempfile.TemporaryDirectory(prefix="nvb_concat_") as tmp:
        normalized = []
        for index, path in enumerate(videos):
            intermediate = Path(tmp) / f"normalized_{index:04d}.mp4"
            cmd = [str(executable), "-hide_banner", "-loglevel", "error", "-y",
                   "-i", str(path), "-map", "0:v:0", "-map", "0:a:0?",
                   "-vf", "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30",
                   "-c:v", "libx264", "-preset", "veryfast", "-crf", "22",
                   "-pix_fmt", "yuv420p", "-c:a", "aac", "-ar", "48000", "-ac", "2",
                   "-movflags", "+faststart", str(intermediate)]
            process = subprocess.run(cmd, capture_output=True, text=True, errors="replace")
            if process.returncode:
                raise RuntimeError(f"Không chuẩn hóa được clip {index+1}: {process.stderr[-700:]}")
            normalized.append(intermediate)
        # FFmpeg concat demuxer requires all streams to match. If one clip has no
        # audio, concat still works for video but audio might be incomplete.
        manifest = Path(tmp) / "clips.txt"
        manifest.write_text("".join("file '" + p.as_posix().replace("'", "'\\''") + "'\n" for p in normalized), encoding="utf-8")
        cmd = [str(executable), "-hide_banner", "-loglevel", "error", "-y",
               "-f", "concat", "-safe", "0", "-i", str(manifest),
               "-c", "copy", "-movflags", "+faststart", str(output)]
        process = subprocess.run(cmd, capture_output=True, text=True, errors="replace")
        if process.returncode:
            output.unlink(missing_ok=True)
            raise RuntimeError("Ghép video thất bại: " + process.stderr[-1200:])
    return output
