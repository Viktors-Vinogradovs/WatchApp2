# app.py
import re, time
import streamlit as st
from typing import Tuple, List, Dict, Any

# Import from our existing modules
from captions import extract_video_id, fetch_captions
from llm_qgen import generate_questions

# Configure page
st.set_page_config(
    page_title="Watch & Ask",
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
    return f"{item['q']}", ordered


def submit_answer(state, choice):
    i = state["idx"]
    if i >= len(state["qa"]):
        return state, "Pabeigts!", ""
    item = state["qa"][i]
    is_correct = (choice == item["a"])
    state["score"] += int(is_correct)
    state["idx"] += 1
    fb = "✅ Pareizi!" if is_correct else f"❌ Nav gluži tā.\n**Pareizi:** {item['a']}"
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


def format_time(seconds):
    """Convert seconds to MM:SS format"""
    mins = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{mins}:{secs:02d}"


# -------- Streamlit UI --------
def main():
    init_session_state()

    st.header("🎥 Skaties video un atbildi uz jautājumiem!")

    # Compact URL input
    col1, col2 = st.columns([5, 1])
    with col1:
        url = st.text_input("YouTube URL", placeholder="https://www.youtube.com/watch?v=xxxxxxxx")
    with col2:
        st.write("")  # Spacing
        generate_btn = st.button("Veidot jautājumus", type="primary", use_container_width=True)

    if generate_btn and url:
        with st.spinner("Meklēju subtitrus un veidoju jautājumus..."):
            quiz_state, message = build_qa(url)
            st.session_state.quiz_state = quiz_state
            st.session_state.show_feedback = False
            st.session_state.current_answer = None

        if quiz_state:
            st.success(message)
        else:
            st.error(message)

    if st.session_state.quiz_state:
        display_quiz()


def display_quiz():
    quiz_state = st.session_state.quiz_state

    # Progress and stats in compact row
    col1, col2, col3, col4 = st.columns([3, 1, 1, 1.5])
    with col1:
        progress = quiz_state["idx"] / len(quiz_state["qa"]) if len(quiz_state["qa"]) > 0 else 0
        st.progress(progress)
    with col2:
        st.metric("Punkti", f"{quiz_state['score']}/{quiz_state['idx']}")
    with col3:
        st.metric("Progress", f"{quiz_state['idx']}/{len(quiz_state['qa'])}")
    with col4:
        if st.button("Sāc jaunu testu", use_container_width=True):
            st.session_state.quiz_state = None
            st.session_state.show_feedback = False
            st.session_state.current_answer = None
            st.rerun()

    st.divider()

    # Check if quiz is finished
    if quiz_state["idx"] >= len(quiz_state["qa"]):
        st.balloons()

        col1, col2 = st.columns(2)
        with col1:
            st.success("🎉 Tests pabeigts!")
            final_score = quiz_state['score']
            total_questions = len(quiz_state['qa'])
            percentage = (final_score / total_questions) * 100

            if percentage >= 80:
                st.success("🏆 Lielisks darbiņš!")
            elif percentage >= 60:
                st.info("👍 Labi!")
            else:
                st.warning("📚 Turpini trenēties!")

        with col2:
            st.metric("Tavi punkti ", f"{final_score}/{total_questions}", f"{percentage:.0f}%")

        return

    # Main layout: Video and Questions side by side
    if quiz_state.get("video_id"):
        current_qa = quiz_state["qa"][quiz_state["idx"]]
        current_time = current_qa["start"]

        # Two columns: Video (left) and Questions (right)
        video_col, question_col = st.columns([1.3, 1], gap="large")

        with video_col:
            st.subheader("📺 Video")

            # Timestamp navigation
            youtube_url = f"https://www.youtube.com/watch?v={quiz_state['video_id']}"
            timestamped_url = f"{youtube_url}&t={int(current_time)}s"

            col_time, col_btn = st.columns([2, 1])
            with col_time:
                st.info(f"⏰ Jautājums no: **{format_time(current_time)}**")
            with col_btn:
                st.link_button("▶️ Atrod īsto brīdi", timestamped_url, use_container_width=True)

            # Embedded video
            video_embed_url = f"https://www.youtube.com/embed/{quiz_state['video_id']}?start={int(current_time)}"
            st.components.v1.iframe(video_embed_url, height=300)

            # Additional links
            st.link_button("🔗 Open in YouTube", youtube_url, use_container_width=True)

        with question_col:
            st.subheader("❓ Jautājums")

            question_data = get_current_question(quiz_state)
            if question_data:
                question_text, choices = question_data

                # Question number and text
                st.write(f"**Jautājums {quiz_state['idx'] + 1}:**")
                st.info(question_text)

                # Answer choices
                current_answer = st.radio(
                    "Izvēlies pareizo atbildi:",
                    options=choices,
                    key=f"answer_{quiz_state['idx']}",
                    index=None
                )

                # Submit button
                submit_btn = st.button(
                    "✅ Iesniedz atbildi",
                    disabled=(current_answer is None),
                    use_container_width=True,
                    type="primary"
                )

                # Language info
                st.caption(f"Language: {quiz_state['lang_name']}")

                # Handle answer submission
                if submit_btn and current_answer:
                    old_state = dict(quiz_state)
                    quiz_state, feedback = submit_answer(quiz_state, current_answer)

                    st.session_state.quiz_state = quiz_state
                    st.session_state.feedback_message = feedback
                    st.session_state.show_feedback = True

                    if "Pareizi!" in feedback:
                        st.success(feedback)
                    else:
                        st.error(feedback)

                    time.sleep(1.5)
                    st.rerun()


if __name__ == "__main__":
    main()
