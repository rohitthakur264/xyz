import ollama
import time

prompt = "Hello! Please say 'Ready'."
print("Sending test request to Ollama (qwen2.5-coder:14b if that is the default)")

try:
    from config.settings import SQL_MODEL
    print(f"SQL_MODEL: {SQL_MODEL}")
except:
    SQL_MODEL = "qwen2.5-coder:14b"
    print(f"Fallback SQL_MODEL: {SQL_MODEL}")

start = time.time()
res = ollama.chat(
    model=SQL_MODEL,
    messages=[{"role": "user", "content": prompt}],
    options={"temperature": 0.0}
)
elapsed = time.time() - start
print(f"Time: {elapsed:.2f}s")
print(f"Response: {res['message']['content']}")
