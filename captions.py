# captions.py - Fetch YouTube captions via yt-dlp (with cookie support for bot bypass)
import base64
import json
import os
import re
import tempfile
import urllib.parse as up
import urllib.request as ur

import yt_dlp

PREFERRED = ["en", "en-US", "lv", "es", "ru"]

# Environment variable for YouTube cookies (Base64 encoded cookies.txt content)
YOUTUBE_COOKIES_ENV = "YOUTUBE_COOKIES_B64"


def extract_video_id(url: str) -> str | None:
    if not url:
        return None
    try:
        u = up.urlparse(url)
        if u.netloc.endswith("youtu.be"):
            return u.path.strip("/").split("/")[0][:11]
        if "youtube.com" in u.netloc:
            qs = up.parse_qs(u.query)
            if "v" in qs and qs["v"]:
                return qs["v"][0][:11]
            if u.path.startswith("/shorts/"):
                return u.path.split("/")[2][:11]
    except Exception:
        pass
    m = re.search(r"(?:v=|youtu\.be/|shorts/)([\w-]{11})", url)
    return m.group(1) if m else None


def _normalize_url(url_or_id: str) -> str:
    """Accept pasted URL or bare video ID; return canonical YouTube URL."""
    s = (url_or_id or "").strip()
    if not s:
        return ""
    if re.match(r"^[\w-]{11}$", s):
        return f"https://www.youtube.com/watch?v={s}"
    if "youtube.com" in s or "youtu.be" in s:
        return s
    vid = extract_video_id(s)
    if vid:
        return f"https://www.youtube.com/watch?v={vid}"
    return s


def _get_cookies_file() -> str | None:
    """
    Get path to cookies file. Creates temp file from env var if YOUTUBE_COOKIES_B64 is set.
    Returns None if no cookies are configured.
    """
    cookies_b64 = os.environ.get(YOUTUBE_COOKIES_ENV, "").strip()
    if not cookies_b64:
        return None
    
    try:
        # Decode Base64 cookies
        cookies_content = base64.b64decode(cookies_b64).decode("utf-8")
        
        # Ensure proper format (Netscape format)
        if not cookies_content.startswith("# "):
            cookies_content = "# Netscape HTTP Cookie File\n" + cookies_content
        
        # Write to temp file
        fd, path = tempfile.mkstemp(suffix=".txt", prefix="yt_cookies_")
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(cookies_content)
        
        return path
    except Exception as e:
        print(f"[COOKIES] Failed to decode cookies: {e}")
        return None


def _parse_json3(content: str) -> list[dict]:
    """Parse YouTube json3 caption format into list of {start, text}."""
    out = []
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        return out
    events = data.get("events") or []
    for ev in events:
        t_start_ms = ev.get("tStartMs", 0)
        segs = ev.get("segs") or []
        parts = []
        for seg in segs:
            if not isinstance(seg, dict):
                continue
            u = seg.get("utf8", "").strip()
            if u:
                parts.append(u)
        if not parts:
            continue
        text = " ".join(parts).replace("\n", " ").strip()
        if text:
            out.append({"start": t_start_ms / 1000.0, "text": text})
    return out


def _fetch_subtitle_url(url: str) -> str:
    """Download subtitle content from URL."""
    req = ur.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; rv:109.0) Gecko/20100101 Firefox/115.0"})
    with ur.urlopen(req, timeout=15) as resp:
        return resp.read().decode("utf-8", errors="replace")


def _get_subtitle_tracks(info: dict) -> dict:
    """Merge automatic_captions and subtitles by lang, preferring manual subs."""
    tracks = {}
    for lang, subs in (info.get("automatic_captions") or {}).items():
        if lang not in tracks and subs:
            tracks[lang] = list(subs) if isinstance(subs, list) else []
    for lang, subs in (info.get("subtitles") or {}).items():
        if subs:
            tracks[lang] = list(subs) if isinstance(subs, list) else []
    return tracks


def _lang_matches(preferred: str, track_lang: str) -> bool:
    """True if track_lang is the same as or a variant of preferred (e.g. en vs en-US)."""
    p = (preferred or "").split("-")[0].lower()
    t = (track_lang or "").split("-")[0].lower()
    return p == t


# yt-dlp YouTube format language_preference: 10 = original, 5 = default
_ORIGINAL_LANG_PREF = 10
_DEFAULT_LANG_PREF = 5


def get_video_primary_language(info: dict) -> str | None:
    """Get the video's default/original language from yt-dlp info."""
    formats = info.get("formats") or []
    for pref in (_ORIGINAL_LANG_PREF, _DEFAULT_LANG_PREF):
        for f in formats:
            if isinstance(f, dict) and f.get("language_preference") == pref and f.get("language"):
                return f["language"]
    for f in formats:
        if isinstance(f, dict) and f.get("language"):
            return f["language"]
    return None


def fetch_captions(url_or_id: str, preferred_languages: list[str] | None = None) -> tuple[list[dict], str]:
    """
    Fetch captions using yt-dlp with cookie support for bot bypass.
    Accepts pasted URL or video ID.

    Returns:
        (captions_list, lang_code) — captions_list is list of {"start": float, "text": str}.
    
    Environment Variables:
        YOUTUBE_COOKIES_B64: Base64-encoded cookies.txt content (Netscape format)
    """
    url = _normalize_url(url_or_id)
    if not url:
        raise RuntimeError("No YouTube URL or video ID provided.")

    # Get cookies file if configured
    cookies_file = _get_cookies_file()
    
    ydl_opts = {
        "skip_download": True,
        "quiet": True,
        "no_warnings": True,
        "extract_flat": False,
    }
    
    # Add cookies if available
    if cookies_file:
        ydl_opts["cookiefile"] = cookies_file
        print(f"[YT-DLP] Using cookies from environment variable")

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            try:
                info = ydl.extract_info(url, download=False)
            except Exception as e:
                raise RuntimeError(f"yt-dlp failed for {url}: {e}") from e
    finally:
        # Clean up temp cookies file
        if cookies_file and os.path.exists(cookies_file):
            try:
                os.remove(cookies_file)
            except Exception:
                pass

    if not info:
        raise RuntimeError("No video info returned.")

    # Use video's default/original language as MAIN, then fall back to PREFERRED
    primary = get_video_primary_language(info)
    if primary and preferred_languages is None:
        rest = [p for p in PREFERRED if not _lang_matches(primary, p)]
        preferred_languages = [primary] + rest
    elif preferred_languages is None:
        preferred_languages = PREFERRED

    tracks = _get_subtitle_tracks(info)
    if not tracks:
        raise RuntimeError("No captions found or accessible for this video.")

    # Prefer json3 for easy parsing; then vtt/srv3
    def pick_format(formats: list) -> dict | None:
        for f in formats:
            if not isinstance(f, dict):
                continue
            ext = (f.get("ext") or "").lower()
            if ext == "json3" and f.get("url"):
                return f
        for f in formats:
            if not isinstance(f, dict) or not f.get("url"):
                continue
            ext = (f.get("ext") or "").lower()
            if ext in ("vtt", "srv3", "srt"):
                return f
        return formats[0] if formats and isinstance(formats[0], dict) and formats[0].get("url") else None

    # Try preferred languages first
    for lang in preferred_languages:
        lang_key = next((k for k in tracks if _lang_matches(lang, k)), None)
        if lang_key is None:
            continue
        fmt = pick_format(tracks[lang_key])
        if not fmt or not fmt.get("url"):
            continue
        try:
            content = _fetch_subtitle_url(fmt["url"])
        except Exception as e:
            print(f"Failed to fetch subs {lang_key}: {e}")
            continue
        ext = (fmt.get("ext") or "").lower()
        if ext == "json3":
            captions = _parse_json3(content)
        else:
            captions = _parse_vtt_like(content)
        if captions:
            return captions, lang_key

    # Fallback: first track that returns data
    for lang_key, formats in tracks.items():
        fmt = pick_format(formats)
        if not fmt or not fmt.get("url"):
            continue
        try:
            content = _fetch_subtitle_url(fmt["url"])
        except Exception:
            continue
        ext = (fmt.get("ext") or "").lower()
        if ext == "json3":
            captions = _parse_json3(content)
        else:
            captions = _parse_vtt_like(content)
        if captions:
            return captions, lang_key

    raise RuntimeError("No captions found or accessible for this video.")


def _parse_vtt_like(content: str) -> list[dict]:
    """Simple VTT/SRT parser."""
    out = []
    lines = content.replace("\r\n", "\n").split("\n")
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if "-->" in line:
            part = line.split("-->")[0].strip()
            start = _vtt_timestamp_to_seconds(part)
            i += 1
            text_parts = []
            while i < len(lines) and lines[i].strip():
                text_parts.append(lines[i].strip())
                i += 1
            text = " ".join(text_parts).strip()
            if text:
                out.append({"start": start, "text": text})
        i += 1
    return out


def _vtt_timestamp_to_seconds(s: str) -> float:
    """Parse VTT/SRT timestamp to seconds."""
    s = s.strip().replace(",", ".")
    parts = s.split(":")
    if len(parts) == 3:
        h, m, sec = parts
    elif len(parts) == 2:
        h, m, sec = "0", parts[0], parts[1]
    else:
        return 0.0
    try:
        return int(h) * 3600 + int(m) * 60 + float(sec)
    except ValueError:
        return 0.0
