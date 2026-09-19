import httpx
import pytest

from app.core.llm_service import LLMServiceError, OllamaLLMService


def _service_returning(payload, status_code: int = 200) -> OllamaLLMService:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, json=payload)

    return OllamaLLMService(model="llama3.1", transport=httpx.MockTransport(handler))


def _service_raising() -> OllamaLLMService:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("simulated connection failure", request=request)

    return OllamaLLMService(model="llama3.1", transport=httpx.MockTransport(handler))


def test_complete_returns_message_content():
    service = _service_returning({"message": {"role": "assistant", "content": '{"ok": true}'}})

    result = service.complete("system prompt", "user prompt")

    assert result == '{"ok": true}'


def test_complete_sends_model_messages_and_json_format():
    import json

    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"message": {"content": "{}"}})

    service = OllamaLLMService(model="llama3.1", transport=httpx.MockTransport(handler))
    service.complete("be concise", "what is here?")

    body = captured["body"]
    assert body["model"] == "llama3.1"
    assert body["format"] == "json"
    assert body["stream"] is False
    assert body["messages"] == [
        {"role": "system", "content": "be concise"},
        {"role": "user", "content": "what is here?"},
    ]


def test_complete_raises_on_connection_failure():
    service = _service_raising()

    with pytest.raises(LLMServiceError):
        service.complete("system", "user")


def test_complete_raises_on_http_error_status():
    service = _service_returning({"error": "model not found"}, status_code=404)

    with pytest.raises(LLMServiceError):
        service.complete("system", "user")


def test_complete_raises_when_response_has_no_content():
    service = _service_returning({"message": {}})

    with pytest.raises(LLMServiceError):
        service.complete("system", "user")


def test_request_asks_for_an_explicit_context_window():
    """Ollama truncates an over-long prompt silently, so the window is requested."""
    body = OllamaLLMService(model="m", num_ctx=12000, think="").request_body("s", "u")

    assert body["options"] == {"num_ctx": 12000}
    assert body["keep_alive"]  # keep the model loaded between questions
    assert "think" not in body  # explicit empty setting sends nothing


def test_thinking_can_be_turned_off_for_reasoning_models():
    body = OllamaLLMService(model="qwen3:30b", think="false").request_body("s", "u")

    assert body["think"] is False
