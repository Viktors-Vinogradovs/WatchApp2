# utils_youtube.py
import os, re, subprocess, tempfile, glob
from youtube_transcript_api import YouTubeTranscriptApi, NoTranscriptFound, TranscriptsDisabled

PREFERRED = ['lv','en','en-US','ru','es']
_YDL = ["yt-dlp", "--no-warnings", "--ignore-errors", "--no-call-home"]
_YT_ID_RE = re.compile(r"(?:v=|youtu\.be/|shorts/)([\w-]{11})")

def extract_video_id(url: str) -> str | None:
    if not url: return None
    m = _YT_ID_RE.search(url)
    return m.group(1) if m else None

def _vtt_to_text(path: str) -> str:
    out = []
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if not line or "-->" in line or line.startswith("WEBVTT") or line.isdigit():
                continue
            out.append(line)
    return " ".join(out)

def get_transcript_text(video_url_or_id: str, preferred=PREFERRED) -> tuple[str, str]:
    vid = video_url_or_id
    if "youtu" in video_url_or_id:
        vid = extract_video_id(video_url_or_id)
    if not vid:
        raise ValueError("Invalid YouTube URL/ID")

    api = YouTubeTranscriptApi()
    # Try direct by preferred langs
    for lang in preferred:
        try:
            t = api.fetch(vid, languages=[lang])  # needs youtube-transcript-api >= 0.6
            data = t.to_raw_data()
            text = " ".join(x["text"] for x in data if x.get("text"))
            if text.strip():
                return text, lang
        except Exception:
            pass

    # Try list → any transcript
    try:
        tl = api.list(vid)
        for lang in preferred:
            try:
                tr = tl.find_transcript([lang])
                data = tr.fetch().to_raw_data()
                text = " ".join(x["text"] for x in data if x.get("text"))
                if text.strip():
                    return text, lang
            except Exception:
                pass
        for tr in tl:
            try:
                data = tr.fetch().to_raw_data()
                text = " ".join(x["text"] for x in data if x.get("text"))
                if text.strip():
                    return text, getattr(tr, "language_code", "unknown")
            except Exception:
                pass
    except (NoTranscriptFound, TranscriptsDisabled):
        pass
    except Exception:
        pass

    # Fallback: yt-dlp auto/manual subs
    url = f"https://www.youtube.com/watch?v={vid}"
    with tempfile.TemporaryDirectory() as td:
        base = os.path.join(td, "%(id)s.%(ext)s")

        cmd = _YDL + ["--skip-download", "--write-auto-sub",
                      "--sub-langs", ",".join(preferred + ["en.*","lv.*","ru.*","es.*"]),
                      "--sub-format", "vtt", "-o", base, url]
        subprocess.run(cmd, check=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

        files = glob.glob(os.path.join(td, f"{vid}*.vtt"))
        if not files:
            cmd2 = _YDL + ["--skip-download", "--write-subs",
                           "--sub-langs", ",".join(preferred + ["en.*","lv.*","ru.*","es.*"]),
                           "--sub-format", "vtt", "-o", base, url]
            subprocess.run(cmd2, check=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            files = glob.glob(os.path.join(td, f"{vid}*.vtt"))

        if not files:
            raise RuntimeError("No captions available (API/yt-dlp)")

        text = _vtt_to_text(files[0])
        if not text.strip():
            raise RuntimeError("Empty captions")
        return text, "auto"
