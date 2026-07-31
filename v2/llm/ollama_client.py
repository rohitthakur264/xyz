import requests
from config.settings import ANSWER_MODEL, LLM_TEMPERATURE
from config.logging import get_logger

logger = get_logger(__name__)

class OllamaClient:
    """Wrapper for Ollama API calls."""
    
    def __init__(self, base_url: str = "http://localhost:11434"):
        self.base_url = base_url

    def generate(self, prompt: str, model: str = ANSWER_MODEL, temperature: float = LLM_TEMPERATURE) -> str:
        """Generate a response using Ollama."""
        url = f"{self.base_url}/api/generate"
        payload = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": temperature
            }
        }
        
        try:
            response = requests.post(url, json=payload, timeout=120)
            response.raise_for_status()
            return response.json().get("response", "")
        except requests.exceptions.RequestException as e:
            logger.error(f"Ollama generation failed for model '{model}': {e}")
            # Check available models on Ollama
            try:
                tags_res = requests.get(f"{self.base_url}/api/tags", timeout=5)
                if tags_res.status_code == 200:
                    avail = [m["name"] for m in tags_res.json().get("models", [])]
                    if avail and model not in avail:
                        fallback_model = avail[0]
                        logger.warning(f"Model '{model}' not found in Ollama. Retrying with available model '{fallback_model}'...")
                        payload["model"] = fallback_model
                        retry_res = requests.post(url, json=payload, timeout=120)
                        retry_res.raise_for_status()
                        return retry_res.json().get("response", "")
            except Exception as inner_e:
                logger.error(f"Ollama fallback attempt failed: {inner_e}")
            raise
