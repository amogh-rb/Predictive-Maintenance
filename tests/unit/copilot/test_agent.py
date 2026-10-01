import asyncio

from copilot.app import agent
from copilot.domain.guardrails import FALLBACK_REPLY


def test_not_configured_without_api_key(monkeypatch):
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    assert agent.is_configured() is False


def test_configured_with_api_key(monkeypatch):
    monkeypatch.setenv("GOOGLE_API_KEY", "fake-key")
    assert agent.is_configured() is True


def test_as_text_handles_plain_string():
    assert agent._as_text("hello") == "hello"


def test_as_text_handles_block_list():
    # Newer Gemini models return content as a list of blocks, not a string.
    content = [{"type": "text", "text": "3 trucks "}, {"type": "text", "text": "at risk"}]
    assert agent._as_text(content) == "3 trucks at risk"


def test_as_text_handles_empty_or_unknown():
    assert agent._as_text(None) == ""
    assert agent._as_text([]) == ""


def test_ask_falls_back_when_not_configured(monkeypatch):
    # No pytest-asyncio dependency added just for this one coroutine — run it
    # directly, same as the rest of this repo's synchronous unit test style.
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    reply = asyncio.run(
        agent.ask("which trucks are at risk?", tenant_id="t1", role="fleet_manager", proposed_by="m@demo")
    )
    assert reply == FALLBACK_REPLY
