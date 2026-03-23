import json
import uuid
from flask import Flask, Response, render_template, request, session, stream_with_context
from openai import OpenAI

app = Flask(__name__)
app.secret_key = "groq-chat-secret-key-change-in-prod"

# In-memory conversation history keyed by session UUID
conversation_histories: dict[str, list] = {}

MODELS = [
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant",
    "groq/compound",
    "groq/compound-mini",
    "openai/gpt-oss-120b",
    "openai/gpt-oss-20b",
    "qwen/qwen3-32b",
    "moonshotai/kimi-k2-instruct",
]

MAX_MESSAGES = 40  # 20 turns


def get_session_id() -> str:
    if "session_id" not in session:
        session["session_id"] = str(uuid.uuid4())
    return session["session_id"]


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/models")
def models():
    return {"models": MODELS}


@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json()
    message = data.get("message", "").strip()
    system_prompt = data.get("system_prompt", "").strip()
    model = data.get("model", MODELS[0])
    temperature = float(data.get("temperature", 0.7))
    top_p = float(data.get("top_p", 0.9))
    max_tokens = int(data.get("max_tokens", 1024))
    api_key = data.get("api_key", "").strip()
    use_stream = data.get("stream", True)

    if not message:
        return {"error": "Message is required"}, 400
    if not api_key:
        return {"error": "API key is required"}, 400

    session_id = get_session_id()
    history = conversation_histories.setdefault(session_id, [])

    history.append({"role": "user", "content": message})
    if len(history) > MAX_MESSAGES:
        history[:] = history[-MAX_MESSAGES:]

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.extend(history)

    client = OpenAI(
        api_key=api_key,
        base_url="https://api.groq.com/openai/v1",
    )

    if not use_stream:
        try:
            completion = client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                top_p=top_p,
                max_tokens=max_tokens,
                stream=False,
            )
            assistant_text = completion.choices[0].message.content or ""
            history.append({"role": "assistant", "content": assistant_text})
            if len(history) > MAX_MESSAGES:
                history[:] = history[-MAX_MESSAGES:]
            return {"content": assistant_text}
        except Exception as e:
            return {"error": str(e)}, 500

    def generate():
        assistant_text = ""
        try:
            stream = client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                top_p=top_p,
                max_tokens=max_tokens,
                stream=True,
            )
            for chunk in stream:
                delta = chunk.choices[0].delta
                if delta.content:
                    assistant_text += delta.content
                    payload = json.dumps({"token": delta.content})
                    yield f"data: {payload}\n\n"

            history.append({"role": "assistant", "content": assistant_text})
            if len(history) > MAX_MESSAGES:
                history[:] = history[-MAX_MESSAGES:]

            yield "data: [DONE]\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    response = Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
    )
    response.headers["X-Accel-Buffering"] = "no"
    response.headers["Cache-Control"] = "no-cache"
    return response


@app.route("/clear", methods=["POST"])
def clear():
    session_id = get_session_id()
    conversation_histories.pop(session_id, None)
    return {"status": "cleared"}


if __name__ == "__main__":
    app.run(debug=True)
