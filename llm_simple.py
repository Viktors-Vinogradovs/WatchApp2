# llm_simple.py - Single-call LLM question generation with timestamps
import json
import os
from typing import List, Dict
from google import genai

# Get config from environment variables
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_QUESTION_MODEL = os.environ.get("GEMINI_QUESTION_MODEL", "gemini-2.5-flash-lite")

# Create client instance
client = genai.Client(api_key=GEMINI_API_KEY)


def format_transcript_with_timestamps(captions: List[Dict]) -> str:
    """Format captions as timestamped transcript for the LLM."""
    lines = []
    for cap in captions:
        start = cap.get("start", 0)
        text = cap.get("text", "").strip()
        if text:
            # Format as [MM:SS] text
            mins = int(start // 60)
            secs = int(start % 60)
            lines.append(f"[{mins}:{secs:02d}] {text}")
    return "\n".join(lines)


def generate_quiz_from_transcript(captions: List[Dict], language: str = "English", max_questions: int = 15) -> List[Dict]:
    """
    Generate quiz questions from FULL transcript in ONE API call.
    
    Args:
        captions: List of caption dicts with 'start' and 'text' keys
        language: Target language for questions
        max_questions: Maximum number of questions to generate
    
    Returns:
        List of question dicts with 'question', 'correct', 'distractors', 'timestamp' keys
    """
    
    # Format transcript with timestamps
    transcript = format_transcript_with_timestamps(captions)
    
    if not transcript.strip():
        return []
    
    # Build the prompt
    prompt = _build_full_transcript_prompt(transcript, language, max_questions)
    
    print(f"[QGEN] Single call: lang={language}, transcript_lines={len(captions)}, max_q={max_questions}")
    
    try:
        response = client.models.generate_content(
            model=GEMINI_QUESTION_MODEL,
            contents=prompt,
            config={
                "temperature": 0.7,
                "top_p": 0.7,
                "max_output_tokens": 4096,
            }
        )
        raw_text = response.text
        print("[QGEN] Raw response length:", len(raw_text))
        
        # Clean up response
        r = raw_text.strip()
        if r.startswith("```"):
            # Remove code fences
            lines = r.split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            r = "\n".join(lines).strip()
            if r.lower().startswith("json"):
                r = r[4:].strip()
        
        data = json.loads(r)
        
        # Validate and extract questions
        questions = []
        for item in data:
            q = item.get("question", "").strip()
            correct = item.get("correct", "").strip()
            distractors = [d.strip() for d in item.get("distractors", []) if isinstance(d, str) and d.strip()]
            timestamp = item.get("timestamp", 0)
            
            # Parse timestamp if it's a string like "1:30"
            if isinstance(timestamp, str):
                timestamp = _parse_timestamp(timestamp)
            
            if q and correct and len(distractors) >= 2:
                questions.append({
                    "question": q,
                    "correct": correct,
                    "distractors": distractors[:3],  # Max 3 distractors
                    "timestamp": float(timestamp)
                })
        
        # Sort by timestamp
        questions.sort(key=lambda x: x["timestamp"])
        
        print(f"[QGEN] Generated {len(questions)} questions")
        return questions
        
    except Exception as e:
        print("[QGEN] Error:", e)
        import traceback
        traceback.print_exc()
        return []


def _parse_timestamp(ts: str) -> float:
    """Parse timestamp string like '1:30' or '90' to seconds."""
    try:
        if ":" in ts:
            parts = ts.replace("[", "").replace("]", "").split(":")
            if len(parts) == 2:
                return int(parts[0]) * 60 + int(parts[1])
            elif len(parts) == 3:
                return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
        return float(ts)
    except:
        return 0


def _build_full_transcript_prompt(transcript: str, language: str, max_questions: int) -> str:
    """Build prompt for generating questions from full transcript."""
    
    lang_lower = language.lower()
    
    # JSON schema that includes timestamp
    schema_info = '''Return ONLY a JSON array. Each item MUST have:
  "timestamp": number (seconds from video start where answer is found - USE THE TIMESTAMPS FROM THE TRANSCRIPT),
  "question": string (short, kid-friendly question),
  "correct": string (the correct answer, short),
  "distractors": array of 2-3 plausible but incorrect answers'''
    
    if lang_lower == "latvian":
        instruction = f"""Tu esi draudzīgs skolotājs. Izveido {max_questions} viktorīnas jautājumus bērniem (7-12 gadi) no šī video transkripta.

SVARĪGI:
- Katram jautājumam JĀIEKĻAUJ timestamp (sekundēs) no transkripta, kur atrodama atbilde
- Jautājumiem jābūt secīgiem - sākot no video sākuma līdz beigām
- Ģenerē jautājumus LATVIEŠU valodā
- Atbildēm jābūt īsām (līdz 12 vārdiem)

{schema_info}

Transkripts ar laika zīmogiem:
{transcript}

Atbildi TIKAI ar JSON masīvu. Bez komentāriem, bez ```."""

    elif lang_lower == "spanish":
        instruction = f"""Eres un maestro amigable. Crea {max_questions} preguntas de quiz para niños (7-12 años) de esta transcripción.

IMPORTANTE:
- Cada pregunta DEBE incluir el timestamp (en segundos) del transcripto donde está la respuesta
- Las preguntas deben ser secuenciales - desde el inicio hasta el final del video
- Genera preguntas en ESPAÑOL
- Las respuestas deben ser cortas (máximo 12 palabras)

{schema_info}

Transcripción con marcas de tiempo:
{transcript}

Responde SOLO con el array JSON. Sin comentarios, sin ```."""

    elif lang_lower == "russian":
        instruction = f"""Ты дружелюбный учитель. Создай {max_questions} вопросов викторины для детей (7-12 лет) по этой транскрипции.

ВАЖНО:
- Каждый вопрос ДОЛЖЕН включать timestamp (в секундах) из транскрипции, где находится ответ
- Вопросы должны идти последовательно - от начала до конца видео
- Генерируй вопросы на РУССКОМ языке
- Ответы должны быть короткими (до 12 слов)

{schema_info}

Транскрипция с временными метками:
{transcript}

Отвечай ТОЛЬКО JSON массивом. Без комментариев, без ```."""

    else:  # English default
        instruction = f"""You are a friendly teacher. Create {max_questions} quiz questions for children (ages 7-12) from this video transcript.

IMPORTANT:
- Each question MUST include the timestamp (in seconds) from the transcript where the answer is found
- Questions should be sequential - from the start to the end of the video
- Generate questions in ENGLISH
- Keep answers short (max 12 words)
- Distractors should be plausible but clearly wrong

{schema_info}

Transcript with timestamps:
{transcript}

Respond ONLY with the JSON array. No comments, no ```."""

    return instruction
