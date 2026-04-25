import io
import json
import re
import uuid
import os
import subprocess
from datetime import datetime
from dotenv import load_dotenv
from flask import Flask, Response, render_template, request, session, stream_with_context, send_file
from flask_sqlalchemy import SQLAlchemy
from openai import OpenAI, APIError
from tavily import TavilyClient
import yfinance as yf

load_dotenv()
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

app = Flask(__name__)
app.secret_key = "groq-chat-secret-key-change-in-prod"
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///chat_history.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# Database Models
class ChatSession(db.Model):
    id = db.Column(db.String(36), primary_key=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    messages = db.relationship('ChatMessage', backref='session', lazy=True, cascade="all, delete-orphan")

class ChatMessage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.String(36), db.ForeignKey('chat_session.id'), nullable=False)
    role = db.Column(db.String(20), nullable=False)
    content = db.Column(db.Text, nullable=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

with app.app_context():
    db.create_all()

MODELS = [
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant",
    "meta-llama/llama-4-scout-17b-16e-instruct",
]

def model_supports_tools(model_name):
    # Only models reliably capable of tool use on Groq
    # llama-3.1-8b-instant and llama-4-scout have unreliable tool call generation
    tool_models = ["llama-3.3-70b", "llama-3.1-70b", "mixtral", "tool-use"]
    return any(tm in model_name.lower() for tm in tool_models)

MAX_MESSAGES = 40  # 20 turns

def get_session_id() -> str:
    if "session_id" not in session:
        session["session_id"] = str(uuid.uuid4())
        new_session = ChatSession(id=session["session_id"])
        db.session.add(new_session)
        db.session.commit()
    return session["session_id"]

def get_history(session_id):
    messages = ChatMessage.query.filter_by(session_id=session_id).order_by(ChatMessage.timestamp.asc()).all()
    return [{"role": m.role, "content": m.content} for m in messages]

def save_message(session_id, role, content):
    new_msg = ChatMessage(session_id=session_id, role=role, content=content)
    db.session.add(new_msg)
    db.session.commit()
    
    # Truncate history if it exceeds MAX_MESSAGES
    all_msgs = ChatMessage.query.filter_by(session_id=session_id).order_by(ChatMessage.timestamp.asc()).all()
    if len(all_msgs) > MAX_MESSAGES:
        to_delete = all_msgs[:-MAX_MESSAGES]
        for m in to_delete:
            db.session.delete(m)
        db.session.commit()

DEFAULT_SYSTEM_PROMPT = (
    "You are a helpful assistant with access to tools.\n"
    "TOOL POLICY (follow strictly):\n"
    "1. get_stock_price: ALWAYS call this when the user asks about a stock price. Never quote prices from memory.\n"
    "2. execute_python: Call this for math, calculations, or running code.\n"
    "3. search_web: You are FORBIDDEN from calling search_web unless the user's message literally contains one of these trigger words: 'search', 'google', 'look up', 'lookup'. "
    "If the user asks about news, current events, recent information, or anything you may not know, and their message does NOT contain a trigger word, you MUST answer from your own knowledge (or say you are not sure) and suggest they ask you to 'search' for the latest info. "
    "Do NOT call search_web on your own initiative under any circumstances."
)

# Tools implementation
def search_web(query):
    try:
        client = TavilyClient(api_key=TAVILY_API_KEY)
        response = client.search(query, max_results=5)
        results = response.get("results", [])
        if not results:
            return "No results found."
        simplified = [{"title": r.get("title", ""), "body": r.get("content", "")[:300]} for r in results]
        return json.dumps(simplified)
    except Exception as e:
        return f"Search failed: {str(e)}"

def get_stock_price(ticker):
    try:
        stock = yf.Ticker(ticker)
        info = stock.fast_info
        return json.dumps({
            "ticker": ticker.upper(),
            "price": round(info.last_price, 2),
            "currency": info.currency,
            "market": info.exchange,
        })
    except Exception as e:
        return f"Failed to get stock price for {ticker}: {str(e)}"

def execute_python(code):
    try:
        # Warning: Using subprocess for code execution is unsafe for production.
        # This is for homework demonstration purposes.
        result = subprocess.run(['python3', '-c', code], capture_output=True, text=True, timeout=10)
        return json.dumps({"stdout": result.stdout, "stderr": result.stderr})
    except Exception as e:
        return f"Error executing code: {str(e)}"

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_web",
            "description": "Web search. Forbidden unless the user's message literally contains 'search', 'google', or 'look up'. Do NOT call this for general questions, news, or current events unless the user used one of those trigger words.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "A short, specific search query (5-10 words max)."
                    }
                },
                "required": ["query"],
                "additionalProperties": False
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_stock_price",
            "description": "Get the current stock price for a publicly traded company. Use this for any question about stock prices.",
            "parameters": {
                "type": "object",
                "properties": {
                    "ticker": {
                        "type": "string",
                        "description": "The stock ticker symbol, e.g. TSLA, AAPL, NVDA.",
                        "maxLength": 10
                    }
                },
                "required": ["ticker"],
                "additionalProperties": False
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "execute_python",
            "description": "Execute Python code for math calculations or data processing.",
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": "The Python code to execute."
                    }
                },
                "required": ["code"],
                "additionalProperties": False
            }
        }
    }
]

# llama-3.3-70b-versatile on Groq intermittently emits its native Llama
# tool-call syntax as text instead of OpenAI tool_calls, e.g.
#   <function=search_web {"query": "..."} </function>
# Groq returns 400 tool_use_failed and puts the raw text in `failed_generation`.
# We parse it so a flaky model output doesn't bubble up as a user-facing error.
LLAMA_TOOL_RE = re.compile(r'<function=(\w+)\s*({.*?})\s*</function>', re.DOTALL)

def parse_llama_tool_fallback(failed_generation):
    if not failed_generation:
        return None
    parsed = []
    for name, args_str in LLAMA_TOOL_RE.findall(failed_generation):
        try:
            json.loads(args_str)
        except json.JSONDecodeError:
            return None
        parsed.append({
            "id": f"call_recovered_{uuid.uuid4().hex[:8]}",
            "type": "function",
            "function": {"name": name, "arguments": args_str},
        })
    return parsed or None

def extract_failed_generation(err):
    body = getattr(err, "body", None)
    if isinstance(body, dict) and body.get("code") == "tool_use_failed":
        return body.get("failed_generation")
    return None

def dispatch_tool(name, args):
    """Run a tool and return (preview_markdown, result_string)."""
    if name == "search_web":
        q = args.get("query", "")
        return f"🔍 **Tool: Searching for:** `{q}`...", search_web(q)
    if name == "get_stock_price":
        t = args.get("ticker", "")
        return f"📈 **Tool: Getting stock price for:** `{t}`...", get_stock_price(t)
    if name == "execute_python":
        c = args.get("code", "")
        return f"💻 **Tool: Executing Python code:**\n```python\n{c}\n```", execute_python(c)
    return f"*Tool not found: {name}*", "Tool not found"

def route_model(message, current_model, api_key):
    if isinstance(message, list):
         return current_model
    
    try:
        client = OpenAI(api_key=api_key, base_url="https://api.groq.com/openai/v1")
        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {"role": "system", "content": "You are a router. Based on the user message, decide which model to use. Respond ONLY with the model name from this list: llama-3.3-70b-versatile, llama-3.1-8b-instant. Use 70b for complex reasoning, math, coding, stock price questions, OR when the user explicitly asks to 'search' / 'look up' / 'google' something (these need tools, and 8b cannot use tools reliably). Use 8b for everything else, including general questions about news or current events where the user did NOT ask to search."},
                {"role": "user", "content": message}
            ],
            max_tokens=20,
            temperature=0
        )
        routed = response.choices[0].message.content.strip()
        if routed in MODELS:
            return routed
    except Exception:
        pass
    return current_model

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/models")
def models():
    return {"models": MODELS}

@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json()
    message = data.get("message", "") # Could be string or list for multimodal
    system_prompt = data.get("system_prompt", "").strip()
    model = data.get("model", MODELS[0])
    temperature = float(data.get("temperature", 0.7))
    top_p = float(data.get("top_p", 0.9))
    max_tokens = int(data.get("max_tokens", 1024))
    use_stream = data.get("stream", True)
    auto_route = data.get("auto_route", False)
    api_key = GROQ_API_KEY

    if not message:
        return {"error": "Message is required"}, 400
    if not api_key:
        return {"error": "Server GROQ_API_KEY is not configured"}, 500

    session_id = get_session_id()
    
    original_model = model
    if auto_route:
        if isinstance(message, list):
            is_vision_model = "vision" in model.lower() or "scout" in model.lower()
            if not is_vision_model:
                model = "meta-llama/llama-4-scout-17b-16e-instruct"
        else:
            model = route_model(message, model, api_key)

    save_message(session_id, "user", json.dumps(message) if not isinstance(message, str) else message)
    history = get_history(session_id)

    # Process history for OpenAI API (parse JSON contents)
    formatted_messages = []
    active_prompt = system_prompt if system_prompt else DEFAULT_SYSTEM_PROMPT
    formatted_messages.append({"role": "system", "content": active_prompt})
    
    for h in history:
        content = h["content"]
        # Only try to parse as JSON if it looks like a list or object
        if content.startswith(("[", "{")):
            try:
                parsed = json.loads(content)
                if isinstance(parsed, list) and "vision" not in model and "scout" not in model:
                    # Flatten to text if not using a vision model
                    text_content = next((item["text"] for item in parsed if item.get("type") == "text"), None)
                    if text_content:
                        formatted_messages.append({"role": h["role"], "content": text_content})
                else:
                    formatted_messages.append({"role": h["role"], "content": parsed})
                continue
            except:
                pass
        formatted_messages.append({"role": h["role"], "content": content})

    client = OpenAI(api_key=api_key, base_url="https://api.groq.com/openai/v1")

    if not use_stream:
        try:
            params = {
                "model": model,
                "messages": formatted_messages,
                "temperature": temperature,
                "top_p": top_p,
                "max_tokens": max_tokens,
                "stream": False,
            }
            if model_supports_tools(model):
                params["tools"] = TOOLS
                params["tool_choice"] = "auto"

            try:
                completion = client.chat.completions.create(**params)
                response_message = completion.choices[0].message
                recovered_tool_calls = None
            except APIError as e:
                recovered_tool_calls = parse_llama_tool_fallback(extract_failed_generation(e))
                if not recovered_tool_calls:
                    raise
                response_message = None

            if recovered_tool_calls is not None:
                tool_calls_normalized = recovered_tool_calls
                formatted_messages.append({"role": "assistant", "content": None, "tool_calls": recovered_tool_calls})
            elif getattr(response_message, "tool_calls", None):
                formatted_messages.append(response_message)
                tool_calls_normalized = [
                    {"id": tc.id, "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                    for tc in response_message.tool_calls
                ]
            else:
                tool_calls_normalized = None

            if tool_calls_normalized:
                tool_output_previews = []
                for tc in tool_calls_normalized:
                    name = tc["function"]["name"]
                    try:
                        args = json.loads(tc["function"]["arguments"])
                    except json.JSONDecodeError:
                        args = {}
                    preview, result = dispatch_tool(name, args)
                    tool_output_previews.append(preview)
                    formatted_messages.append({
                        "tool_call_id": tc["id"],
                        "role": "tool",
                        "name": name,
                        "content": result,
                    })

                second_completion = client.chat.completions.create(
                    model=model,
                    messages=formatted_messages,
                    temperature=temperature,
                    top_p=top_p,
                    max_tokens=max_tokens,
                )
                assistant_text = second_completion.choices[0].message.content or ""
                if tool_output_previews:
                    assistant_text = "\n\n".join(tool_output_previews) + "\n\n" + assistant_text
            else:
                assistant_text = response_message.content or ""

            save_message(session_id, "assistant", assistant_text)
            return {"content": assistant_text, "model_used": model, "original_model": original_model}
        except Exception as e:
            return {"error": str(e)}, 500

    def generate():
        assistant_text = ""
        if model != original_model:
            yield f"data: {json.dumps({'routed_model': model, 'original_model': original_model})}\n\n"
        try:
            params = {
                "model": model,
                "messages": formatted_messages,
                "temperature": temperature,
                "top_p": top_p,
                "max_tokens": max_tokens,
                "stream": True,
            }
            if model_supports_tools(model):
                params["tools"] = TOOLS
                params["tool_choice"] = "auto"

            tool_calls = []
            recovered = None
            try:
                stream = client.chat.completions.create(**params)
                for chunk in stream:
                    if not chunk.choices: continue
                    delta = chunk.choices[0].delta

                    if hasattr(delta, "tool_calls") and delta.tool_calls:
                        for tc in delta.tool_calls:
                            while len(tool_calls) <= tc.index:
                                tool_calls.append({"id": "", "type": "function", "function": {"name": "", "arguments": ""}})
                            if tc.id: tool_calls[tc.index]["id"] = tc.id
                            if tc.function.name: tool_calls[tc.index]["function"]["name"] += tc.function.name
                            if tc.function.arguments: tool_calls[tc.index]["function"]["arguments"] += tc.function.arguments

                    if hasattr(delta, "content") and delta.content:
                        assistant_text += delta.content
                        payload = json.dumps({"token": delta.content, "model": model})
                        yield f"data: {payload}\n\n"
            except APIError as e:
                recovered = parse_llama_tool_fallback(extract_failed_generation(e))
                if not recovered:
                    raise
                assistant_text = ""

            if recovered:
                valid_tool_calls = recovered
            else:
                valid_tool_calls = [tc for tc in tool_calls if tc.get("id") and tc["function"]["name"]]

            if valid_tool_calls:
                formatted_messages.append({
                    "role": "assistant",
                    "content": assistant_text if assistant_text else None,
                    "tool_calls": valid_tool_calls,
                })

                for tc in valid_tool_calls:
                    name = tc["function"]["name"]
                    try:
                        args = json.loads(tc["function"]["arguments"])
                    except json.JSONDecodeError:
                        args = {}
                    preview, result = dispatch_tool(name, args)
                    tool_token = "\n" + preview + "\n"
                    yield f"data: {json.dumps({'token': tool_token})}\n\n"
                    formatted_messages.append({
                        "tool_call_id": tc["id"],
                        "role": "tool",
                        "name": name,
                        "content": result,
                    })

                # Stream the final response after tool execution
                # Re-pass the temperature and other params
                final_stream = client.chat.completions.create(
                    model=model,
                    messages=formatted_messages,
                    stream=True,
                    temperature=temperature,
                    top_p=top_p,
                    max_tokens=max_tokens,
                )
                for chunk in final_stream:
                    delta = chunk.choices[0].delta
                    if delta.content:
                        assistant_text += delta.content
                        payload = json.dumps({"token": delta.content})
                        yield f"data: {payload}\n\n"

            yield "data: [DONE]\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
        finally:
            save_message(session_id, "assistant", assistant_text if assistant_text else "[Tool response]")

    response = Response(stream_with_context(generate()), mimetype="text/event-stream")
    response.headers["X-Accel-Buffering"] = "no"
    return response


@app.route("/export")
def export_chat():
    session_id = get_session_id()
    history = get_history(session_id)
    content = f"# Chat History - {session_id}\n\n"
    for msg in history:
        content += f"### {msg['role'].capitalize()}\n{msg['content']}\n\n---\n\n"
    
    buffer = io.BytesIO(content.encode("utf-8"))
    buffer.seek(0)
    return send_file(buffer, as_attachment=True, download_name="chat_history.md", mimetype="text/markdown")

def get_csrf_token():
    if "csrf_token" not in session:
        session["csrf_token"] = str(uuid.uuid4())
    return session["csrf_token"]

@app.route("/csrf_token")
def csrf_token():
    return {"token": get_csrf_token()}

@app.route("/clear", methods=["POST"])
def clear():
    data = request.get_json() or {}
    token = data.get("csrf_token", "")
    if not token or token != session.get("csrf_token"):
        return {"error": "Invalid CSRF token"}, 403
    session_id = get_session_id()
    ChatMessage.query.filter_by(session_id=session_id).delete()
    db.session.commit()
    return {"status": "cleared"}

if __name__ == "__main__":
    app.run(debug=True)
