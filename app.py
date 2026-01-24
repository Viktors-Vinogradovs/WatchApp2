# app.py - Lightweight Flask version of Watch & Ask
import secrets
from flask import Flask, render_template, request, jsonify, session

from captions import extract_video_id, fetch_captions
from llm_simple import generate_quiz_from_transcript

app = Flask(__name__)
app.secret_key = secrets.token_hex(32)


# -------- Helper Functions --------

def lang_code_to_name(code: str) -> str:
    """Convert language code to full name."""
    c = (code or "").lower()
    if c.startswith("lv"):
        return "Latvian"
    if c.startswith("es"):
        return "Spanish"
    if c.startswith("ru"):
        return "Russian"
    return "English"


def build_quiz(url: str):
    """
    Build quiz data from a YouTube URL.
    Makes ONE API call to generate all questions with timestamps.
    Returns: (quiz_data, error_message)
    """
    vid = extract_video_id(url)
    if not vid:
        return None, "Invalid YouTube URL."

    try:
        caps, code = fetch_captions(vid)
    except Exception as e:
        return None, f"Could not fetch captions: {e}"

    if not caps:
        return None, "No captions found. Try another video with subtitles."

    lang_name = lang_code_to_name(code)
    
    # Single API call to generate all questions with timestamps
    questions = generate_quiz_from_transcript(
        captions=caps,
        language=lang_name,
        max_questions=15
    )
    
    if not questions:
        return None, "Couldn't generate questions from this transcript. Try another video."

    # Format questions for the quiz
    qa = []
    for q in questions:
        choices = [q["correct"]] + q["distractors"]
        qa.append({
            "start": round(q["timestamp"], 1),
            "question": q["question"],
            "correct": q["correct"],
            "choices": choices
        })

    quiz_data = {
        "video_id": vid,
        "lang_name": lang_name,
        "questions": qa,
        "total": len(qa)
    }
    return quiz_data, None


# -------- Routes --------

@app.route("/")
def index():
    """Serve the main page."""
    return render_template("index.html")


@app.route("/api/generate", methods=["POST"])
def api_generate():
    """Generate quiz from YouTube URL."""
    data = request.get_json()
    url = data.get("url", "").strip()
    
    if not url:
        return jsonify({"error": "Please provide a YouTube URL."}), 400
    
    quiz_data, error = build_quiz(url)
    
    if error:
        return jsonify({"error": error}), 400
    
    # Store in session
    session["quiz"] = quiz_data
    session["current_idx"] = 0
    session["score"] = 0
    session["is_second_attempt"] = False
    
    return jsonify({
        "success": True,
        "video_id": quiz_data["video_id"],
        "total_questions": quiz_data["total"],
        "language": quiz_data["lang_name"]
    })


@app.route("/api/question", methods=["GET"])
def api_question():
    """Get current question."""
    quiz = session.get("quiz")
    if not quiz:
        return jsonify({"error": "No quiz loaded."}), 400
    
    idx = session.get("current_idx", 0)
    
    if idx >= len(quiz["questions"]):
        return jsonify({
            "finished": True,
            "score": session.get("score", 0),
            "total": quiz["total"]
        })
    
    q = quiz["questions"][idx]
    
    # Shuffle choices based on index for variety
    choices = list(q["choices"])
    if idx % 2 == 1 and len(choices) >= 2:
        choices[0], choices[1] = choices[1], choices[0]
    
    return jsonify({
        "finished": False,
        "question_num": idx + 1,
        "total": quiz["total"],
        "question": q["question"],
        "timestamp": q["start"],
        "choices": choices,
        "video_id": quiz["video_id"],
        "score": session.get("score", 0),
        "is_second_attempt": session.get("is_second_attempt", False)
    })


@app.route("/api/submit", methods=["POST"])
def api_submit():
    """Submit an answer."""
    quiz = session.get("quiz")
    if not quiz:
        return jsonify({"error": "No quiz loaded."}), 400
    
    idx = session.get("current_idx", 0)
    if idx >= len(quiz["questions"]):
        return jsonify({"error": "Quiz already finished."}), 400
    
    data = request.get_json()
    answer = data.get("answer", "")
    
    q = quiz["questions"][idx]
    is_correct = (answer == q["correct"])
    is_second_attempt = session.get("is_second_attempt", False)
    
    if is_second_attempt:
        # Second attempt - move on regardless
        session["score"] = session.get("score", 0) + int(is_correct)
        session["current_idx"] = idx + 1
        session["is_second_attempt"] = False
        
        return jsonify({
            "correct": is_correct,
            "correct_answer": q["correct"],
            "message": "Correct!" if is_correct else "Still incorrect, but moving on.",
            "move_next": True,
            "score": session["score"]
        })
    
    if is_correct:
        # Correct on first try
        session["score"] = session.get("score", 0) + 1
        session["current_idx"] = idx + 1
        
        return jsonify({
            "correct": True,
            "message": "Correct!",
            "move_next": True,
            "score": session["score"]
        })
    else:
        # Wrong on first try - give second chance
        session["is_second_attempt"] = True
        
        return jsonify({
            "correct": False,
            "correct_answer": q["correct"],
            "message": f"Not quite. The correct answer was: {q['correct']}",
            "move_next": False,
            "timestamp": q["start"],
            "score": session.get("score", 0)
        })


@app.route("/api/reset", methods=["POST"])
def api_reset():
    """Reset the quiz."""
    session.clear()
    return jsonify({"success": True})


if __name__ == "__main__":
    app.run(debug=True, port=5000)
