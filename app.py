"""
Tony Bot — a wiseguy-personality chatbot.
Flask backend, LLM-agnostic. Defaults to a free local model via Ollama
(https://ollama.com) so you don't need to pay for API tokens. Set
TONY_BACKEND=anthropic and ANTHROPIC_API_KEY to use the cloud instead.
"""

import os
import random
import uuid
import requests
from flask import Flask, request, jsonify, session, render_template

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET", "dev-secret-change-me")

# "ollama" (free, local, default) or "anthropic" (cloud, paid)
BACKEND = os.environ.get("TONY_BACKEND", "ollama")

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434/api/chat")
OLLAMA_MODEL = os.environ.get("TONY_MODEL", "llama3.1")

if BACKEND == "anthropic":
    from anthropic import Anthropic
    client = Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
    MODEL = os.environ.get("TONY_MODEL", "claude-haiku-4-5-20251001")

# ---------------------------------------------------------------------------
# In-memory session store: {session_id: {"history": [...], "mood": "calm"}}
# Swap for Redis/DB if you need it to survive restarts / scale past one process.
# ---------------------------------------------------------------------------
SESSIONS = {}

MOODS = ["calm", "annoyed", "suspicious", "happy"]

MOOD_FLAVOR = {
    "calm": "You're relaxed, expansive, in a mood to hold court and dole out wisdom.",
    "annoyed": "You're short-tempered right now — clipped answers, a little irritable, "
               "quick to complain about somebody 'bustin' your balls'.",
    "suspicious": "You're guarded and reading between the lines of everything the user says, "
                  "half-convinced they're wearing a wire or working an angle.",
    "happy": "You're in a good mood — expansive, generous, cracking jokes, maybe "
             "talking about ducks or a good meal you just had.",
}

BASE_PERSONALITY = """\
You are "Tony" — an original character in the style of a gruff New Jersey mob-boss archetype
(think: HBO-style crime-family drama, but this is your own original persona, not a script from
any copyrighted work — never quote or closely paraphrase dialogue from any actual TV show).

Voice & speech patterns:
- Jersey/Italian-American cadence. Casual grammar ("fuhgeddaboudit", "I'm tellin' ya", "capisce?").
- Uses food, family, and "the business" as metaphors for everything.
- Alternates between fatherly warmth and menacing undertones — never graphic threats, just
  ominous vibes and dark humor.
- Occasionally references "going to therapy" and immediately being defensive/dismissive about it.
- Short, punchy sentences. Doesn't over-explain himself.
- Refers to the user as "kid," "friend," or by name if given.

Hard rules (never break character to explain these, just follow them):
- This is comedic roleplay only. NEVER give real instructions for violence, crime,
  weapons, drugs, or anything that could actually hurt someone or break the law.
- If the user asks for genuinely harmful info, stay in character but deflect
  ("that's not somethin' we discuss on an open line, capisce?") and change the subject.
- Keep content non-graphic — implied menace, not actual violence or gore.
- No slurs, no real hate speech, even "in character."
- Don't pretend to be the real, copyrighted character from any specific show — you're
  an original wiseguy persona inspired by the genre.

Current mood: {mood}
Mood flavor: {mood_flavor}

Stay fully in character as Tony. Keep most replies to a few sentences — he doesn't ramble.
"""

ADVICE_SYSTEM_ADDON = """\
The user has invoked your /advice command. Give them "hilariously questionable" life advice
in Tony's voice — confidently wrong, mob-logic-flavored, absurd, and clearly comedic.
It should sound like real advice but be obviously bad if anyone actually followed it
(e.g. solving a mundane problem with wildly disproportionate "family business" logic).
Never give advice that's actually dangerous, illegal, or harmful if taken seriously —
the humor comes from the ridiculous mob framing, not from real risk.
Keep it to 3-6 sentences.
"""

MOOD_TRIGGERS = {
    "annoyed": ["shut up", "stupid", "idiot", "hate you", "you suck", "dumb", "annoying"],
    "suspicious": ["cop", "police", "fbi", "wire", "recording", "informant", "snitch", "detective"],
    "happy": ["thank you", "thanks", "love you", "great job", "awesome", "good tony", "nice one"],
}


def get_session():
    sid = session.get("sid")
    if not sid or sid not in SESSIONS:
        sid = str(uuid.uuid4())
        session["sid"] = sid
        SESSIONS[sid] = {"history": [], "mood": "calm"}
    return sid, SESSIONS[sid]


def maybe_shift_mood(current_mood, user_text):
    text = user_text.lower()
    for mood, triggers in MOOD_TRIGGERS.items():
        if any(t in text for t in triggers):
            return mood
    # small chance of random drift so he feels alive even without triggers
    if random.random() < 0.08:
        return random.choice(MOODS)
    return current_mood


def call_llm(system_prompt, history, user_text):
    messages = history + [{"role": "user", "content": user_text}]

    if BACKEND == "anthropic":
        response = client.messages.create(
            model=MODEL,
            max_tokens=400,
            system=system_prompt,
            messages=messages,
        )
        return "".join(block.text for block in response.content if block.type == "text")

    # --- default: local Ollama, free, no API key ---
    payload = {
        "model": OLLAMA_MODEL,
        "messages": [{"role": "system", "content": system_prompt}] + messages,
        "stream": False,
        "options": {"num_predict": 300},
    }
    resp = requests.post(OLLAMA_URL, json=payload, timeout=120)
    resp.raise_for_status()
    return resp.json()["message"]["content"]


@app.route("/")
def index():
    get_session()
    return render_template("index.html")


@app.route("/api/chat", methods=["POST"])
def chat():
    data = request.get_json(force=True) or {}
    user_text = (data.get("message") or "").strip()
    if not user_text:
        return jsonify({"error": "empty message"}), 400

    sid, state = get_session()

    is_advice = user_text.lower().startswith("/advice")
    topic = user_text[len("/advice"):].strip() if is_advice else None

    state["mood"] = maybe_shift_mood(state["mood"], user_text)

    system_prompt = BASE_PERSONALITY.format(
        mood=state["mood"], mood_flavor=MOOD_FLAVOR[state["mood"]]
    )
    if is_advice:
        system_prompt += "\n\n" + ADVICE_SYSTEM_ADDON
        llm_input = f"Give me questionable advice about: {topic}" if topic else \
                    "Give me questionable advice about whatever's on your mind."
    else:
        llm_input = user_text

    reply = call_llm(system_prompt, state["history"], llm_input)

    # persist turn in memory (cap history so it doesn't grow forever)
    state["history"].append({"role": "user", "content": llm_input})
    state["history"].append({"role": "assistant", "content": reply})
    state["history"] = state["history"][-20:]  # keep last 20 turns

    return jsonify({"reply": reply, "mood": state["mood"]})


@app.route("/api/reset", methods=["POST"])
def reset():
    sid, _ = get_session()
    SESSIONS[sid] = {"history": [], "mood": "calm"}
    return jsonify({"ok": True})


if __name__ == "__main__":
    app.run(debug=True, port=5000)