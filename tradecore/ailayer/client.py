import logging

import httpx

from tradecore.core.config import get_settings

logger = logging.getLogger("tradecore.ailayer.client")


async def generate_response(model: str, prompt: str) -> str | None:
    """
    Generate response from Ollama server using the provided model and prompt.
    Returns None if Ollama is not enabled, fails, or times out.
    """
    settings = get_settings()
    if not settings.ollama.enabled:
        logger.debug("Ollama is disabled in settings.")
        return None

    url = f"{settings.ollama.host}/api/generate"
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
    }

    timeout_sec = float(settings.ollama.request_timeout_sec)

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, json=payload, timeout=timeout_sec)
            if resp.status_code == 200:
                data = resp.json()
                return data.get("response")
            else:
                logger.warning(f"Ollama response unhealthy ({resp.status_code}): {resp.text}")
                return None
    except httpx.TimeoutException as te:
        logger.warning(f"Ollama request timed out after {timeout_sec}s: {te}")
        return None
    except Exception as e:
        logger.warning(f"Ollama request failed: {e}")
        return None
