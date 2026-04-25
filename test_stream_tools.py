import json
from openai import OpenAI

api_key = "GROQ_API_KEY_REDACTED"
client = OpenAI(api_key=api_key, base_url="https://api.groq.com/openai/v1")

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_web",
            "description": "Search the web for real-time information.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"}
                },
                "required": ["query"]
            }
        }
    }
]

messages = [
    {"role": "user", "content": "what's the weather in taipei today?"}
]

print("--- Testing Streaming Tool Call ---")
try:
    stream = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=messages,
        tools=TOOLS,
        stream=True
    )
    
    for chunk in stream:
        delta = chunk.choices[0].delta
        if delta.tool_calls:
            print(f"Tool Call Chunk: {delta.tool_calls}")
        if delta.content:
            print(f"Content Chunk: {delta.content}")

except Exception as e:
    print(f"Error: {e}")
