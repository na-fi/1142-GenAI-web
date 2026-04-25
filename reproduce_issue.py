import json
from openai import OpenAI

api_key = "GROQ_API_KEY_REDACTED"
client = OpenAI(api_key=api_key, base_url="https://api.groq.com/openai/v1")

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_web",
            "description": "Search the web for real-time info or facts not in your training data.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "The search query."}
                },
                "required": ["query"]
            }
        }
    }
]

messages = [
    {"role": "system", "content": "You are a helpful assistant. Use tools ONLY when necessary."},
    {"role": "user", "content": "what's the weather in taipei today?"}
]

print("--- Testing Tool Call Generation ---")
try:
    response = client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=messages,
        tools=TOOLS,
        tool_choice="auto"
    )
    
    msg = response.choices[0].message
    print(f"Assistant Message: {msg}")
    
    if msg.tool_calls:
        print(f"Tool Calls detected: {len(msg.tool_calls)}")
        for tc in msg.tool_calls:
            print(f"Function: {tc.function.name}")
            print(f"Arguments: {tc.function.arguments}")
    else:
        print("No tool calls generated.")

except Exception as e:
    print(f"Error during first call: {e}")
