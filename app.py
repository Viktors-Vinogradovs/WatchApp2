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
    return state, f"Loaded {len(qa)} questions. Language: {lang_name}"


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

    # Check if this is a second attempt after a wrong answer
    if 'is_second_attempt' in st.session_state and st.session_state['is_second_attempt']:
        # This is a second attempt, so update score and move on regardless of correctness
        state["score"] += int(is_correct)
        state["idx"] += 1
        st.session_state['is_second_attempt'] = False  # Reset flag
        return state, "✅ Correct!" if is_correct else "❌ Still incorrect, but moving on."

    if is_correct:
        # Correct on first try
        state["score"] += 1
        state["idx"] += 1
        return state, "✅ Correct!"
    else:
        # Incorrect on first try. Don't advance the index, but set flag for second chance.
        st.session_state['is_second_attempt'] = True
        return state, f"❌ Not quite.\n**Correct:** {item['a']}"


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
    # New state variable for second chance
    if 'is_second_attempt' not in st.session_state:
        st.session_state['is_second_attempt'] = False
    # New state variable to control video jump
    if 'video_jump_time' not in st.session_state:
        st.session_state['video_jump_time'] = None


def handle_url_submit():
    """Handle URL submission via Enter key or button click"""
    url = st.session_state.get("youtube_url", "").strip()
    if url:
        with st.spinner("🔄 Fetching captions and generating questions..."):
            quiz_state, message = build_qa(url)
            st.session_state.quiz_state = quiz_state
            st.session_state.show_feedback = False
            st.session_state.current_answer = None
            st.session_state.generation_message = message
            # Reset jump time when a new video is loaded
            st.session_state['video_jump_time'] = None


def jump_to_timestamp(start_time):
    """Update the video jump time in session state"""
    st.session_state['video_jump_time'] = int(start_time)


# -------- Streamlit UI --------
def main():
    init_session_state()

    st.title("🎥 Watch & Ask — YouTube Captions → LLM Questions")

    # URL Input Section
    st.subheader("🔗 Enter YouTube URL")

    with st.form(key="url_form", clear_on_submit=False):
        col1, col2 = st.columns([4, 1])
        with col1:
            url = st.text_input(
                "YouTube URL",
                placeholder="https://www.youtube.com/watch?v=XXXXXXXXXXX",
                key="youtube_url",
                label_visibility="collapsed"
            )
        with col2:
            generate_btn = st.form_submit_button("🎯 Generate Questions", type="primary", use_container_width=True)

    if generate_btn:
        handle_url_submit()

    if hasattr(st.session_state, 'generation_message'):
        if st.session_state.quiz_state:
            st.caption(f"✅ {st.session_state.generation_message}")
        else:
            st.error(st.session_state.generation_message)

    if st.session_state.quiz_state:
        display_quiz()


def display_quiz():
    quiz_state = st.session_state.quiz_state

    if quiz_state["idx"] >= len(quiz_state["qa"]):
        st.balloons()
        st.subheader("🎉 Quiz Complete!")
        col1, col2 = st.columns(2)
        with col1:
            st.metric("📊 Final Score", f"{quiz_state['score']}/{len(quiz_state['qa'])}")
        with col2:
            percentage = (quiz_state['score'] / len(quiz_state['qa'])) * 100
            st.metric("📈 Percentage", f"{percentage:.1f}%")
        if percentage >= 80:
            st.success("🏆 Excellent work!")
        elif percentage >= 60:
            st.info("👍 Good job!")
        else:
            st.warning("📚 Keep practicing!")
        if st.button("🔄 Start New Quiz", type="primary"):
            st.session_state.quiz_state = None
            st.session_state.show_feedback = False
            st.session_state.current_answer = None
            st.session_state['video_jump_time'] = None
            st.session_state['is_second_attempt'] = False
            if hasattr(st.session_state, 'generation_message'):
                delattr(st.session_state, 'generation_message')
            st.rerun()
        return

    video_col, question_col = st.columns([1.2, 1], gap="medium")

    with video_col:
        st.subheader("📺 Video Player")
        if quiz_state.get("video_id"):
            # Use the jump time from session state if available, otherwise use the question's start time
            jump_time = st.session_state.get('video_jump_time')
            if jump_time is None:
                 jump_time = quiz_state["qa"][quiz_state["idx"]]["start"]

            # Construct the embedded video URL with the start time
            video_embed_url = f"https://www.youtube.com/embed/{quiz_state['video_id']}?start={int(jump_time)}"

            st.components.v1.iframe(video_embed_url, height=280)

            st.caption(f"⏰ Question from ~{quiz_state['qa'][quiz_state['idx']]['start']}s")

    with question_col:
        st.subheader("❓ Current Question")
        question_data = get_current_question(quiz_state)
        if question_data:
            question_text, choices = question_data

            with st.container():
                st.write(question_text)

                # The "Jump to timestamp" button is now removed from here.

                # This button only appears when the user has answered incorrectly.
                if st.session_state.get('is_second_attempt'):
                    # Get timestamp of the correct answer
                    correct_answer_start_time = quiz_state["qa"][quiz_state["idx"]]["start"]
                    if st.button(f"↩️ Try again? Jump back to the correct answer's section!", type="secondary", use_container_width=True):
                        jump_to_timestamp(correct_answer_start_time)
                        st.rerun()

                current_answer = st.radio(
                    "Choose your answer:",
                    options=choices,
                    key=f"answer_{quiz_state['idx']}",
                    index=None
                )

                submit_btn = st.button(
                    "✅ Submit Answer",
                    disabled=(current_answer is None),
                    type="primary",
                    use_container_width=True
                )

                if submit_btn and current_answer:
                    quiz_state, feedback = submit_answer(quiz_state, current_answer)
                    st.session_state.quiz_state = quiz_state
                    st.session_state.feedback_message = feedback
                    st.session_state.show_feedback = True

                    if "Correct!" in feedback:
                        st.success(feedback)
                    else:
                        st.error(feedback)

                    time.sleep(1)
                    st.rerun()

    st.divider()
    progress = quiz_state["idx"] / len(quiz_state["qa"])
    st.progress(progress)
    col1, col2 = st.columns(2)
    with col1:
        st.metric("📊 Score", f"{quiz_state['score']}/{quiz_state['idx']}")
    with col2:
        st.metric("🎯 Progress", f"{quiz_state['idx'] + 1}/{len(quiz_state['qa'])}")


if __name__ == "__main__":
    main()