# app.py
import re, time
import streamlit as st
from typing import Tuple, List, Dict, Any

# Import from our existing modules
from captions import extract_video_id, fetch_captions
from llm_qgen import generate_questions

# Configure page
st.set_page_config(
    page_title="Watch & Ask - YouTube + Gemini",
    page_icon="🎥",
    layout="wide"
)


# -------- Helper Functions --------
def chunk_by_time(captions, window_sec=75, overlap_sec=0):
    if not captions:
        return []
    chunks, buf, start = [], [], captions[0]["start"]
    for line in captions:
        buf.append(line)
        cur_end = line["start"] + line.get("duration", 0)
        if cur_end - start >= window_sec:
            chunks.append((start, list(buf)))
            buf, start = [], cur_end - overlap_sec
    if buf:
        chunks.append((start, list(buf)))
    return chunks


def chunk_text(chunk):
    return " ".join(x["text"] for x in chunk if x.get("text", "").strip())


def lang_code_to_name(code: str) -> str:
    c = (code or "").lower()
    if c.startswith("lv"): return "Latvian"
    if c.startswith("es"): return "Spanish"
    if c.startswith("ru"): return "Russian"
    return "English"


# -------- Fallback generator (if LLM fails) --------
def fallback_questions(txt: str, k=2):
    sents = [s.strip() for s in re.split(r"[.!?]\s+", txt) if len(s.strip()) > 12]
    out = []
    for s in sents[:k]:
        q = f"What was mentioned here: \"{s[:70]}...\""
        correct = s
        distractors = ["Not mentioned", "Something unrelated", "I'm not sure"]
        out.append({"question": q, "correct": correct, "distractors": distractors})
    return out


def build_qa(url: str):
    vid = extract_video_id(url)
    if not vid:
        return None, "❌ Invalid YouTube URL."

    try:
        caps, code = fetch_captions(vid)
    except Exception as e:
        return None, f"❌ Could not fetch captions: {e}"

    if not caps:
        return None, "❌ No captions found. Try another video with subtitles."

    lang_name = lang_code_to_name(code)
    chunks = chunk_by_time(caps, window_sec=75)
    qa, seen = [], []
    previous_questions = []

    # Limit: first 8 chunks for MVP
    for start, ch in chunks[:8]:
        txt = chunk_text(ch)
        if not txt or len(txt) < 60:
            continue
        items = generate_questions(txt, previous_questions=previous_questions, language=lang_name)
        if not items:
            items = fallback_questions(txt, k=2)
        for it in items:
            q = it["question"].strip()
            if not q or q in seen:
                continue
            choices = [it["correct"]] + list(it["distractors"])
            qa.append({"start": round(start, 1), "q": q, "a": it["correct"], "choices": choices})
            seen.append(q)
            previous_questions.append(q)

        # Stop at ~20 questions
        if len(qa) >= 20:
            break

    if not qa:
        return None, "❌ Couldn't generate any questions from this transcript."

    state = {"video_id": vid, "lang_name": lang_name, "qa": qa, "idx": 0, "score": 0, "previous_qs": previous_questions}
    return state, f"✅ Loaded {len(qa)} questions. Language: {lang_name}"


def get_current_question(state):
    i = state["idx"]
    if i >= len(state["qa"]):
        return None
    item = state["qa"][i]
    # Shuffle choices once per question index (deterministic shuffle by index)
    ordered = list(item["choices"])
    # Simple swap for variation
    if i % 2 == 1 and len(ordered) >= 2:
        ordered[0], ordered[1] = ordered[1], ordered[0]
    return f"Q{i + 1}: {item['q']}\n(From ~{item['start']}s)", ordered


def submit_answer(state, choice):
    i = state["idx"]
    if i >= len(state["qa"]):
        return state, "Finished.", ""
    item = state["qa"][i]
    is_correct = (choice == item["a"])
    state["score"] += int(is_correct)
    state["idx"] += 1
    fb = "✅ Correct!" if is_correct else f"❌ Not quite.\n**Correct:** {item['a']}"
    return state, fb


# Initialize session state
def init_session_state():
    if 'quiz_state' not in st.session_state:
        st.session_state.quiz_state = None
    if 'current_answer' not in st.session_state:
        st.session_state.current_answer = None
    if 'show_feedback' not in st.session_state:
        st.session_state.show_feedback = False
    if 'feedback_message' not in st.session_state:
        st.session_state.feedback_message = ""


# -------- Streamlit UI --------
def main():
    init_session_state()

    st.title("🎥 Watch & Ask — YouTube Captions → LLM Questions")

    # URL Input Section
    st.subheader("📝 Enter YouTube URL")
    col1, col2 = st.columns([3, 1])

    with col1:
        url = st.text_input(
            "YouTube URL",
            placeholder="https://www.youtube.com/watch?v=XXXXXXXXXXX",
            key="youtube_url"
        )

    with col2:
        st.write("")  # Add spacing
        st.write("")  # Add spacing
        generate_btn = st.button("🎯 Generate Questions", type="primary")

    # Generate questions when button is clicked
    if generate_btn and url:
        with st.spinner("🔄 Fetching captions and generating questions..."):
            quiz_state, message = build_qa(url)
            st.session_state.quiz_state = quiz_state
            st.session_state.show_feedback = False
            st.session_state.current_answer = None

        if quiz_state:
            st.success(message)
        else:
            st.error(message)

    # Display quiz if questions are loaded
    if st.session_state.quiz_state:
        display_quiz()


def display_quiz():
    quiz_state = st.session_state.quiz_state

    # Progress bar
    progress = quiz_state["idx"] / len(quiz_state["qa"])
    st.progress(progress)

    # Score display
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("📊 Score", f"{quiz_state['score']}/{quiz_state['idx']}")
    with col2:
        st.metric("🎯 Question", f"{quiz_state['idx'] + 1}/{len(quiz_state['qa'])}")
    with col3:
        st.metric("🌐 Language", quiz_state['lang_name'])

    st.divider()

    # YouTube Video Player
    if quiz_state.get("video_id"):
        st.subheader("📺 Video Player")
        youtube_url = f"https://www.youtube.com/watch?v={quiz_state['video_id']}"

        # Create two columns - video player and current question info
        col1, col2 = st.columns([2, 1])

        with col1:
            # Embed YouTube video
            video_embed_url = f"https://www.youtube.com/embed/{quiz_state['video_id']}"
            st.components.v1.iframe(video_embed_url, width=560, height=315)

        with col2:
            # Show current question timestamp
            if quiz_state["idx"] < len(quiz_state["qa"]):
                current_time = quiz_state["qa"][quiz_state["idx"]]["start"]
                st.info(f"⏰ Current question is from ~{current_time}s in the video")

                # Direct link to timestamp
                timestamped_url = f"{youtube_url}&t={int(current_time)}s"
                st.markdown(f"[▶️ Jump to timestamp]({timestamped_url})")

            st.markdown(f"[🔗 Open in YouTube]({youtube_url})")

        st.divider()

    # Check if quiz is finished
    if quiz_state["idx"] >= len(quiz_state["qa"]):
        st.balloons()
        st.success(f"🎉 Quiz Complete! Final Score: {quiz_state['score']}/{len(quiz_state['qa'])}")

        # Calculate percentage
        percentage = (quiz_state['score'] / len(quiz_state['qa'])) * 100
        if percentage >= 80:
            st.success("🏆 Excellent work!")
        elif percentage >= 60:
            st.info("👍 Good job!")
        else:
            st.warning("📚 Keep practicing!")

        # Reset button
        if st.button("🔄 Start New Quiz"):
            st.session_state.quiz_state = None
            st.session_state.show_feedback = False
            st.session_state.current_answer = None
            st.rerun()
        return

    # Display current question
    question_data = get_current_question(quiz_state)
    if question_data:
        question_text, choices = question_data

        st.subheader("❓ Current Question")
        st.write(question_text)

        # Display choices as radio buttons
        current_answer = st.radio(
            "Choose your answer:",
            options=choices,
            key=f"answer_{quiz_state['idx']}",
            index=None
        )

        # Submit button
        col1, col2, col3 = st.columns([1, 1, 2])
        with col1:
            submit_btn = st.button("✅ Submit Answer", disabled=(current_answer is None))

        # Handle answer submission
        if submit_btn and current_answer:
            # Process the answer
            old_state = dict(quiz_state)  # Make a copy
            quiz_state, feedback = submit_answer(quiz_state, current_answer)

            # Update session state
            st.session_state.quiz_state = quiz_state
            st.session_state.feedback_message = feedback
            st.session_state.show_feedback = True

            # Show feedback
            if "Correct!" in feedback:
                st.success(feedback)
            else:
                st.error(feedback)

            # Add a small delay and rerun to show next question
            time.sleep(1)
            st.rerun()


if __name__ == "__main__":
    main()