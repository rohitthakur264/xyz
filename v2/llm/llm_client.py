import requests
import re
import json
import threading
import os
import time
from config.settings import ANSWER_MODEL, LLM_TEMPERATURE, LLM_API_KEY, LLM_BASE_URL
from config.logging import get_logger

logger = get_logger(__name__)

class LLMClient:
    """Wrapper for Groq API calls."""
    _current_key_idx = 0
    _lock = threading.Lock()
    
    def __init__(self, base_url: str = LLM_BASE_URL):
        self.base_url = base_url

    def generate(self, prompt: str, model: str = ANSWER_MODEL, temperature: float = LLM_TEMPERATURE) -> str:
        """Generate a response using Groq."""
        keys = []
        if LLM_API_KEY:
            keys = [k.strip() for k in LLM_API_KEY.split(",") if k.strip()]
            
        for k, v in sorted(os.environ.items()):
            if k.startswith("LLM_API_KEY_") and v.strip():
                if v.strip() not in keys:
                    keys.append(v.strip())
                    
        if not keys:
            logger.error("No API keys found in environment.")
            return "Error: LLM_API_KEY is missing."
            
        url = self.base_url
        is_gemini = "generativelanguage.googleapis.com" in url
        is_ollama = ("/" not in model) and (":" in model or model in ["llama3", "llama3.1", "phi3", "gemma2"])

        # Create a fallback sequence of models to use for 429s to maximize TPM
        model_sequence = [model]
        if "gpt-oss-20b" in model and "safeguard" not in model:
            model_sequence.append("openai/gpt-oss-safeguard-20b")
        elif "safeguard" in model:
            model_sequence.append("openai/gpt-oss-20b")
            
        # We will try every key for every model in our sequence
        max_retries = len(keys) * len(model_sequence)
        start_time = time.time()
        MAX_TOTAL_TIME = 150
        
        for attempt in range(max_retries):
            if time.time() - start_time > MAX_TOTAL_TIME:
                logger.error("LLM request exceeded total time budget, aborting.")
                raise TimeoutError("AI service is taking too long. Please try again.")

            with LLMClient._lock:
                current_key = keys[LLMClient._current_key_idx % len(keys)]
                LLMClient._current_key_idx += 1
                
            current_model = model_sequence[(attempt // len(keys)) % len(model_sequence)]
            
            if is_gemini:
                gemini_url = f"https://generativelanguage.googleapis.com/v1beta/models/{current_model}:generateContent?key={current_key}"
                payload = {
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {"temperature": temperature}
                }
                headers = {"Content-Type": "application/json"}
                url = gemini_url
            else:
                if is_ollama:
                    url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1/chat/completions")
                
                payload = {
                    "model": current_model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": temperature
                }
                headers = {
                    "Authorization": f"Bearer {current_key}",
                    "Content-Type": "application/json"
                }

            try:
                response = requests.post(url, json=payload, headers=headers, timeout=30)
                response.raise_for_status()
                data = response.json()
                
                if is_gemini:
                    content = data["candidates"][0]["content"]["parts"][0]["text"]
                else:
                    content = data["choices"][0]["message"].get("content", "")
                    if "usage" in data:
                        usage = data["usage"]
                        prompt_tokens = usage.get('prompt_tokens', 0)
                        completion_tokens = usage.get('completion_tokens', 0)
                        total_tokens = usage.get('total_tokens', 0)
                        
                        # Extract cached tokens if the API supports it (like OpenAI/Anthropic)
                        cached_tokens = 0
                        if "prompt_tokens_details" in usage:
                            cached_tokens = usage["prompt_tokens_details"].get("cached_tokens", 0)
                            
                        uncached_tokens = prompt_tokens - cached_tokens
                        
                        logger.info(f"API Token Usage [{current_model}] - Cached Input: {cached_tokens}, Uncached Input: {uncached_tokens}, Output: {completion_tokens}, Total: {total_tokens}")
                
                return content.strip()
                
            except requests.exceptions.HTTPError as e:
                if e.response is not None and e.response.status_code in [401, 429, 503]:
                    logger.warning(f"{e.response.status_code} Error Hit (model: {current_model}). Switching key/model...")
                    if e.response.status_code == 429:
                        time.sleep(1.5)
                    continue
                elif e.response is not None and e.response.status_code == 413:
                    logger.warning(f"413 Payload Too Large (len={len(prompt)}). Retrying with trimmed prompt...")
                    prompt = prompt[:1200] + "\n\n... [data trimmed for size] ...\n\n" + prompt[-1800:]
                    continue
                elif e.response is not None and e.response.status_code == 400:
                    logger.warning(f"400 Bad Request Hit (model: {current_model}). Switching key/model...")
                    continue
                else:
                    logger.error(f"HTTP Error: {e}")
                    raise
            except Exception as e:
                logger.error(f"LLM request error: {e}")
                if attempt >= max_retries - 1:
                    raise
                continue
                
        raise TimeoutError("AI service is currently experiencing heavy load (rate limited). Please try again in a few minutes.")
