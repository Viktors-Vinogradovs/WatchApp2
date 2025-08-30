# llm_qgen.py
import json
from langchain.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_google_genai import ChatGoogleGenerativeAI
from typing import List
from config import GEMINI_API_KEY, GEMINI_QUESTION_MODEL

llm_question = ChatGoogleGenerativeAI(
    model=GEMINI_QUESTION_MODEL,
    api_key=GEMINI_API_KEY,
    temperature=0.7,
    top_p=0.7,
)

def _sys_msg(language: str, previous_questions: List[str]) -> str:
    base_schema = (
        "Return ONLY a JSON array (no code fences, no prose). "
        "Each item MUST be an object with keys:\n"
        '  "question": string (kid-friendly, short),\n'
        '  "correct": string,\n'
        '  "distractors": array of 2-3 short strings (plausible, not true),\n'
        '  "difficulty": "easy" | "medium" (pick sensibly for 7–12yo).\n'
        "Do NOT repeat or paraphrase these previous questions: " + json.dumps(previous_questions, ensure_ascii=False) + ". "
        "Questions must be answerable from the provided text only."
    )

    if language.lower() == "latvian":
        return (
            "Tu esi draudzīgs skolotājs, kurš ģenerē TRIS īsus jautājumus bērniem. "
            "Atbildi TIKAI kā JSON masīvu. Bez komentāriem, bez ```.\n"
            + base_schema +
            "\nĢenerē jautājumus LATVIEŠU valodā."
        )
    if language.lower() == "spanish":
        return (
            "Eres un maestro amigable que genera TRES preguntas cortas para niños. "
            "Responde SOLO como un arreglo JSON. Sin comentarios, sin ```.\n"
            + base_schema +
            "\nGenera preguntas en ESPAÑOL."
        )
    if language.lower() == "russian":
        return (
            "Ты дружелюбный учитель, который генерирует ТРИ коротких вопроса для детей. "
            "Отвечай ТОЛЬКО JSON-массивом. Без комментариев, без ```.\n"
            + base_schema +
            "\nГенерируй вопросы на РУССКОМ."
        )
    return (
        "You are a friendly teacher generating THREE short questions for children. "
        "Respond ONLY as a JSON array. No comments, no ```.\n"
        + base_schema +
        "\nGenerate questions in ENGLISH."
    )

def generate_questions(fragment: str, previous_questions: List[str]=[], language: str="English"):
    # Debug
    print(f"[QGEN] lang={language}, prev={len(previous_questions)}, frag_len={len(fragment)}")

    prompt = ChatPromptTemplate.from_messages([
        ("system", _sys_msg(language, previous_questions)),
        ("human", f"Text:\n{fragment}\n\nRules:\n- Keep questions grounded strictly in this text.\n- Avoid proper nouns if not present.\n- Keep answers short (<= 12 words).")
    ])

    response = (prompt | llm_question | StrOutputParser()).invoke({})
    print("[QGEN] Raw:", response[:400], "..." if len(response) > 400 else "")

    try:
        # Strip stray fences if any
        r = response.strip()
        if r.startswith("```"):
            r = r.strip("`").strip()
            if r.lower().startswith("json"):
                r = r[4:].strip()
        data = json.loads(r)
        # Validate minimal schema
        out = []
        for item in data:
            q = item.get("question", "").strip()
            correct = item.get("correct", "").strip()
            distractors = [d.strip() for d in item.get("distractors", []) if isinstance(d, str)]
            if q and correct and distractors:
                out.append({"question": q, "correct": correct, "distractors": distractors})
        if not out:
            raise ValueError("Empty after validation")
        print(f"[QGEN] ok items={len(out)}")
        return out
    except Exception as e:
        print("[QGEN] JSON parse/validate error:", e)
        return []
