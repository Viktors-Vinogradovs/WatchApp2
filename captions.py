# captions.py - Fetch YouTube captions via youtube_transcript_api
import re
import urllib.parse as up
from youtube_transcript_api import YouTubeTranscriptApi, NoTranscriptFound, TranscriptsDisabled

PREFERRED = ["en", "en-US", "lv", "es", "ru"]


def extract_video_id(url: str) -> str | None:
    """Extract YouTube video ID from various URL formats."""
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


def _lang_matches(preferred: str, track_lang: str) -> bool:
    """True if track_lang is the same as or a variant of preferred (e.g. en vs en-US)."""
    p = (preferred or "").split("-")[0].lower()
    t = (track_lang or "").split("-")[0].lower()
    return p == t


def fetch_captions(url_or_id: str, preferred_languages: list[str] | None = None) -> tuple[list[dict], str]:
    """
    Fetch captions using youtube_transcript_api. Accepts URL or video ID.

    Returns:
        (captions_list, lang_code) — captions_list is list of {"start": float, "text": str}.
    """
    if preferred_languages is None:
        preferred_languages = PREFERRED

    # Extract video ID from URL if needed
    video_id = extract_video_id(url_or_id)
    if not video_id:
        # Maybe it's already a video ID
        if url_or_id and re.match(r"^[\w-]{11}$", url_or_id.strip()):
            video_id = url_or_id.strip()
        else:
            raise RuntimeError("Could not extract video ID from URL.")

    # Create API instance
    ytt_api = YouTubeTranscriptApi()

    try:
        # Method 1: Try to list all available transcripts first
        try:
            transcript_list = ytt_api.list(video_id)
            
            # Try preferred languages first (manual subs preferred)
            for lang in preferred_languages:
                try:
                    transcript = transcript_list.find_transcript([lang])
                    fetched = transcript.fetch()
                    captions = _convert_to_caption_list(fetched)
                    if captions:
                        return captions, lang
                except Exception:
                    continue
            
            # Try any matching language variant
            for lang in preferred_languages:
                for transcript in transcript_list:
                    if _lang_matches(lang, transcript.language_code):
                        try:
                            fetched = transcript.fetch()
                            captions = _convert_to_caption_list(fetched)
                            if captions:
                                return captions, transcript.language_code
                        except Exception:
                            continue
            
            # Fallback: get first available transcript
            for transcript in transcript_list:
                try:
                    fetched = transcript.fetch()
                    captions = _convert_to_caption_list(fetched)
                    if captions:
                        return captions, transcript.language_code
                except Exception:
                    continue

        except (NoTranscriptFound, TranscriptsDisabled):
            pass

        # Method 2: Direct fetch with preferred languages
        for lang in preferred_languages:
            try:
                fetched = ytt_api.fetch(video_id, languages=[lang])
                captions = _convert_to_caption_list(fetched)
                if captions:
                    return captions, lang
            except Exception:
                continue

        # Method 3: Fetch any available
        try:
            fetched = ytt_api.fetch(video_id)
            captions = _convert_to_caption_list(fetched)
            if captions:
                return captions, "auto"
        except Exception:
            pass

    except Exception as e:
        raise RuntimeError(f"Error fetching captions for video {video_id}: {e}") from e

    raise RuntimeError(f"No captions found or accessible for video {video_id}")


def _convert_to_caption_list(fetched_transcript) -> list[dict]:
    """Convert FetchedTranscript to list of {start, text} dicts."""
    try:
        # Try to_raw_data() first (newer API)
        if hasattr(fetched_transcript, 'to_raw_data'):
            raw_data = fetched_transcript.to_raw_data()
            return [{"start": item.get("start", 0), "text": item.get("text", "")} for item in raw_data]
        
        # Fallback: iterate directly (older API or already a list)
        if isinstance(fetched_transcript, list):
            return [{"start": item.get("start", 0), "text": item.get("text", "")} for item in fetched_transcript]
        
        # Try iterating
        return [{"start": item.get("start", 0), "text": item.get("text", "")} for item in fetched_transcript]
    except Exception:
        return []
