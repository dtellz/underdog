import os

from langchain_openai import ChatOpenAI


def get_llm(temperature: float = 0.3, **kwargs) -> ChatOpenAI:
    """Return a ChatOpenAI client bound to the local llama-server.

    llama-server exposes an OpenAI-compatible API at /v1, so ChatOpenAI works
    as long as base_url is overridden. The api_key is required by the SDK but
    ignored by llama-server. Timeout defaults to 600s because local 35B
    models doing tool-call reasoning can easily take 1–3 minutes per turn.
    """
    return ChatOpenAI(
        base_url=os.getenv("LLAMA_SERVER_URL", "http://localhost:8080/v1"),
        api_key=os.getenv("LLAMA_SERVER_API_KEY", "sk-no-key-required"),
        model=os.getenv("LLAMA_MODEL", "qwen3.6-35b-a3b"),
        temperature=temperature,
        timeout=float(os.getenv("LLAMA_TIMEOUT", "600")),
        max_retries=int(os.getenv("LLAMA_MAX_RETRIES", "1")),
        **kwargs,
    )
