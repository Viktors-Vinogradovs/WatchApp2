# test_latvian_video.py
# Test script for your specific Latvian video

from youtube_transcript_api import YouTubeTranscriptApi


def test_latvian_video():
    video_id = "6iqALO9bvPI"
    print(f"Testing Latvian video: {video_id}")

    # Test the new configurable fetch_captions function
    def fetch_captions(video_id: str, preferred_languages=None):
        if preferred_languages is None:
            preferred_languages = ["en", "en-US", "lv", "es", "ru"]

        ytt_api = YouTubeTranscriptApi()

        # Try preferred languages first
        for lang in preferred_languages:
            try:
                fetched_transcript = ytt_api.fetch(video_id, languages=[lang])
                transcript_data = fetched_transcript.to_raw_data()
                return transcript_data, lang
            except Exception as e:
                print(f"Failed to get {lang}: {e}")
                continue

        # Fallback: get any available
        try:
            transcript_list = ytt_api.list(video_id)
            for transcript in transcript_list:
                try:
                    fetched_transcript = transcript.fetch()
                    transcript_data = fetched_transcript.to_raw_data()
                    return transcript_data, transcript.language_code
                except Exception:
                    continue
        except Exception as e:
            raise RuntimeError(f"No captions found: {e}")

    # Test 1: Try with Latvian first
    print("\n--- Test 1: Latvian first ---")
    try:
        caps, lang = fetch_captions(video_id, ['lv'])
        print(f"✅ Success! Got {len(caps)} segments in {lang}")
        print(f"Sample: {caps[0]['text'][:50]}...")
    except Exception as e:
        print(f"❌ Failed: {e}")


if __name__ == "__main__":
    test_latvian_video()