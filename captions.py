# captions.py
import re, urllib.parse as up
from youtube_transcript_api import (
    YouTubeTranscriptApi,
    NoTranscriptFound,
    TranscriptsDisabled,
)

PREFERRED = ['en', 'en-US', 'lv', 'es', 'ru']


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


def fetch_captions(video_id: str, preferred_languages=None):
    """
    Returns: (captions_list, lang_code)
    Uses the NEW YouTube Transcript API (instance-based).

    Args:
        video_id: YouTube video ID
        preferred_languages: List of language codes to try (e.g., ['lv', 'en', 'es'])
                           If None, uses default PREFERRED list
    """
    if preferred_languages is None:
        preferred_languages = PREFERRED

    # Create API instance
    ytt_api = YouTubeTranscriptApi()

    try:
        # Method 1: Try direct fetch with preferred languages
        for lang in preferred_languages:
            try:
                fetched_transcript = ytt_api.fetch(video_id, languages=[lang])
                # Convert FetchedTranscript object to raw data format
                transcript_data = fetched_transcript.to_raw_data()
                return transcript_data, lang
            except Exception:
                continue

        # Method 2: Use list() to get all available transcripts and pick the best one
        try:
            transcript_list = ytt_api.list(video_id)

            # Try preferred languages first
            for lang in preferred_languages:
                try:
                    transcript = transcript_list.find_transcript([lang])
                    fetched_transcript = transcript.fetch()
                    transcript_data = fetched_transcript.to_raw_data()
                    return transcript_data, lang
                except Exception:
                    continue

            # If no preferred language found, get the first available transcript
            for transcript in transcript_list:
                try:
                    fetched_transcript = transcript.fetch()
                    transcript_data = fetched_transcript.to_raw_data()
                    lang_code = getattr(transcript, 'language_code', 'unknown')
                    return transcript_data, lang_code
                except Exception:
                    continue

        except (NoTranscriptFound, TranscriptsDisabled):
            pass
        except Exception as e:
            print(f"Error with transcript_list: {e}")

        # Method 3: Last resort - try to fetch any available transcript
        try:
            fetched_transcript = ytt_api.fetch(video_id)
            transcript_data = fetched_transcript.to_raw_data()
            return transcript_data, "auto"
        except Exception as e:
            print(f"Final fallback failed: {e}")

    except Exception as e:
        print(f"General error: {e}")
        raise RuntimeError(f"Error fetching captions for video {video_id}: {e}")

    # If we get here, nothing worked
    raise RuntimeError(f"No captions found or accessible for video {video_id}")