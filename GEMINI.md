# Project Overview: LLM Chat Web App (NYCU GenAI HW01)

This project is a simple, functional Flask-based chat application that allows users to interact with Large Language Models (LLMs) through a web interface. It uses an OpenAI-compatible API (configured for Groq) to handle chat completions, supporting both streaming (via Server-Sent Events) and non-streaming responses.

## Main Technologies
- **Backend:** [Flask](https://flask.palletsprojects.com/) (Python)
- **LLM SDK:** [OpenAI Python Library](https://github.com/openai/openai-python) (configured with Groq base URL)
- **Frontend:** Vanilla JavaScript and CSS (all contained in `templates/index.html`)
- **Markdown Rendering:** [marked](https://marked.js.org/) (loaded via CDN)
- **Session Management:** In-memory dictionary (`conversation_histories`) keyed by session UUIDs stored in Flask's session cookies.

## Project Structure
- `HW01/app.py`: The main entry point containing all Flask routes, API integration logic, and in-memory history management.
- `HW01/templates/index.html`: The complete single-page application frontend, including CSS, HTML, and JS logic.
- `HW01/requirements.txt`: Python dependencies (`flask`, `openai`).
- `HW01/README.md`: Original documentation with detailed endpoint specifications and setup instructions.

## Building and Running

### Prerequisites
- Python 3.8+
- A [Groq API Key](https://console.groq.com/keys) (required for chat functionality)

### Setup & Run
1.  **Navigate to the project directory:**
    ```bash
    cd HW01
    ```
2.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```
3.  **Start the server:**
    ```bash
    python app.py
    ```
4.  **Access the UI:**
    Open `http://127.0.0.1:5000/` in your browser.

## Development Conventions

### API Integration
- The application interfaces with Groq's API at `https://api.groq.com/openai/v1`.
- It uses the `openai` Python SDK for compatibility.
- API keys are provided by the user via the browser UI and passed to the backend for each request (Note: this is for local/homework use only and is not secure for production).

### State Management
- **Conversation History:** Stored in-memory in the `conversation_histories` dictionary.
- **Persistence:** History is lost when the server restarts or the `/clear` endpoint is called.
- **Context Window:** History is truncated to `MAX_MESSAGES = 40` (approximately 20 turns) to manage context limits.

### Frontend Patterns
- **Streaming:** Implemented using `EventSource` on the client and `stream_with_context` on the server for real-time token rendering.
- **Prompt Nodes:** A sidebar feature that allows users to jump back to previously sent messages.
- **Styling:** Custom CSS within `index.html` provides a modern, dark-themed chat interface.

## Key Configuration
- `app.secret_key`: Used for Flask session signing. (Update for any production use).
- `MODELS`: The list of available model identifiers is defined in `app.py`.
- `MAX_MESSAGES`: Defines the maximum number of messages kept in history.
