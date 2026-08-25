from __future__ import annotations

import json
import time
import types

import pytest

from src.core.config import CORPUS_DIR, MANIFEST_PATH, PROJECT_ROOT
from src.core.models import (
    ActionEnum,
    ChatMessage,
    ChunkMetadata,
    Citation,
    DocumentChunk,
    ResponseEnvelope,
    SessionState,
)
from src.ingestion.parser import MarkdownCorpusParser
from src.rag import replay
from src.rag.llm import LLMClient, MockLLM, build_escalation_envelope

# Entities the review flagged as invented; they must never appear in RAG-layer
# source code or in any envelope produced by it.
INVENTED_ENTITIES = ["Senior Support Engineer", "safety engineering team"]

# Hardcoded product knowledge that was evicted from MockLLM; must not return.
EVICTED_LITERALS = [
    "Gigabit Ethernet via Cat5e",
    "mesh synchronization",
    "3.4.2",
    "2.5GbE WAN port",
    "wifey box",
    "Pair the N1 node",
]


@pytest.fixture(scope="module")
def corpus_chunks() -> list[DocumentChunk]:
    parser = MarkdownCorpusParser(CORPUS_DIR, MANIFEST_PATH)
    return parser.parse_all()


def chunks_for(chunks: list[DocumentChunk], source_id: str, locator: str | None = None) -> list[DocumentChunk]:
    return [
        c for c in chunks
        if c.metadata.source_id == source_id and (locator is None or c.metadata.locator == locator)
    ]


def make_session(**kwargs) -> SessionState:
    return SessionState(session_id="test-session", **kwargs)


def make_chunk(source_id: str, locator: str, text: str) -> DocumentChunk:
    return DocumentChunk(
        text=text,
        metadata=ChunkMetadata(
            chunk_id=f"{source_id}_test",
            source_id=source_id,
            doc_title=source_id.replace("-", " ").title(),
            locator=locator,
            sha256="0" * 64,
        ),
    )


class FakeCompletions:
    """Scripted stand-in for client.chat.completions. Each result is either a
    content string or an Exception to raise. Every fake message carries a
    'reasoning' attribute that must never surface in a response."""

    REASONING_TEXT = "hidden-chain-of-thought-must-never-be-used"

    def __init__(self, results: list):
        self.results = list(results)
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        result = self.results.pop(0)
        if isinstance(result, Exception):
            raise result
        message = types.SimpleNamespace(content=result, reasoning=self.REASONING_TEXT)
        return types.SimpleNamespace(choices=[types.SimpleNamespace(message=message)])


class FakeClient:
    def __init__(self, results: list):
        self.chat = types.SimpleNamespace(completions=FakeCompletions(results))


def make_live_client(results: list, models: tuple[str, ...] = ("model-a", "model-b")) -> LLMClient:
    client = LLMClient()
    client.mode = "live"
    client.client = FakeClient(results)
    client.fallback_models = list(models)
    client.rate_limit_delay = 0.0
    return client


# ---------------------------------------------------------------------------
# MockLLM: grounded extraction only
# ---------------------------------------------------------------------------

def test_mock_extraction_returns_corpus_text_for_known_query(corpus_chunks):
    retrieved = chunks_for(corpus_chunks, "led-reference", "N1 node LEDs")
    assert retrieved, "corpus must contain the 'N1 node LEDs' section"

    env = MockLLM.generate_response(
        "My N1 node shows solid amber, what does it mean?", make_session(), retrieved
    )

    assert env.action == ActionEnum.INSTRUCT
    assert env.citations == [Citation(source_id="led-reference", locator="N1 node LEDs")]
    # Verbatim corpus content, not the old invented "move closer" advice
    assert "software/recovery state" in env.response
    assert "Check app notice and firmware version" in env.response
    assert "move" not in env.response.lower()


def test_mock_abstains_with_ask_and_empty_citations_on_empty_retrieval():
    env = MockLLM.generate_response("What is the capital of France?", make_session(), [])
    assert env.action == ActionEnum.ASK
    assert env.citations == []
    # An abstention must not pretend to cite or answer
    assert "?" in env.response


def test_mock_resolution_on_gratitude():
    env = MockLLM.generate_response("Thanks, it's all good now!", make_session(), [])
    assert env.action == ActionEnum.RESOLVED
    assert env.citations == []


def test_mock_hardcoded_branches_are_gone(corpus_chunks):
    # Garbled input no longer hits a special case: with no retrieval it abstains
    env = MockLLM.generate_response("wifey box nod1 blnk yellow no worky", make_session(), [])
    assert env.action == ActionEnum.ASK
    assert env.citations == []

    # Firmware question is answered from retrieved corpus text, not a frozen constant
    retrieved = chunks_for(corpus_chunks, "firmware-release-notes")
    assert retrieved
    env2 = MockLLM.generate_response("What is the latest firmware version?", make_session(), retrieved)
    assert env2.citations and env2.citations[0].source_id == "firmware-release-notes"


# ---------------------------------------------------------------------------
# Escalation copy comes from the corpus, no invented entities
# ---------------------------------------------------------------------------

def test_mock_exhaustion_escalates_with_corpus_policy(corpus_chunks):
    session = make_session(attempted_steps=["power_cycled", "cable_checked", "channel_optimized"])
    retrieved = chunks_for(corpus_chunks, "troubleshooting-guide")

    env = MockLLM.generate_response("I tried everything and it's still not working", session, retrieved)

    assert env.action == ActionEnum.ESCALATE
    assert env.citations == [Citation(source_id="warranty-safety-policy", locator="When to escalate")]
    # Directs to the in-app support channel per the corpus escalation policy
    assert "OrbitMesh app" in env.response
    # Corpus-sourced reason and info-to-provide sentence
    assert "documented troubleshooting path" in env.response
    assert "steps already attempted" in env.response
    for entity in INVENTED_ENTITIES:
        assert entity.lower() not in env.response.lower()


def test_escalation_envelope_builder_uses_corpus_section():
    env = build_escalation_envelope()
    assert env.action == ActionEnum.ESCALATE
    assert env.citations == [Citation(source_id="warranty-safety-policy", locator="When to escalate")]
    for entity in INVENTED_ENTITIES:
        assert entity.lower() not in env.response.lower()


def test_no_invented_entities_or_evicted_literals_in_rag_sources():
    for rel in ("src/rag/llm.py", "src/rag/replay.py"):
        content = (PROJECT_ROOT / rel).read_text(encoding="utf-8")
        for entity in INVENTED_ENTITIES:
            assert entity not in content, f"{entity!r} found in {rel}"
        for literal in EVICTED_LITERALS:
            assert literal not in content, f"{literal!r} found in {rel}"


# ---------------------------------------------------------------------------
# LLMClient hardening
# ---------------------------------------------------------------------------

def test_unknown_action_fails_closed_to_ask():
    payload = json.dumps({
        "response": "Check the LED.",
        "citations": [{"source_id": "led-reference", "locator": "N1 node LEDs"}],
        "action": "reboot",
    })
    client = make_live_client([payload], models=("model-a",))

    env = client.complete("what now?", make_session(), [])

    assert env.action == ActionEnum.ASK
    assert env.response == "Check the LED."


def test_missing_action_fails_closed_to_ask():
    payload = json.dumps({"response": "Check the LED.", "citations": []})
    client = make_live_client([payload], models=("model-a",))
    env = client.complete("what now?", make_session(), [])
    assert env.action == ActionEnum.ASK


def test_empty_content_is_candidate_failure_and_reasoning_is_never_used():
    good = json.dumps({"response": "Restart the node once.", "citations": [], "action": "instruct"})
    client = make_live_client(["", good])

    env = client.complete("n1 solid red", make_session(), [])

    assert env.action == ActionEnum.INSTRUCT
    assert env.response == "Restart the node once."
    assert FakeCompletions.REASONING_TEXT not in env.response
    calls = client.client.chat.completions.calls
    assert [c["model"] for c in calls] == ["model-a", "model-b"]


def test_live_call_passes_timeout_and_max_tokens():
    good = json.dumps({"response": "ok", "citations": [], "action": "instruct"})
    client = make_live_client([good], models=("model-a",))
    client.complete("hello", make_session(), [])
    call = client.client.chat.completions.calls[0]
    assert call["max_tokens"] == client.max_tokens
    assert call["timeout"] == client.request_timeout
    assert call["temperature"] == 0.0


def test_cascade_exhaustion_returns_corpus_escalation(monkeypatch):
    monkeypatch.setattr(time, "sleep", lambda _s: None)
    client = make_live_client([RuntimeError("boom"), RuntimeError("boom")])

    env = client.complete("n1 flashing amber", make_session(), [])

    assert env.action == ActionEnum.ESCALATE
    assert env.citations == [Citation(source_id="warranty-safety-policy", locator="When to escalate")]
    assert "OrbitMesh app" in env.response
    for entity in INVENTED_ENTITIES:
        assert entity.lower() not in env.response.lower()


def test_live_mode_without_client_fails_closed_to_escalation():
    client = LLMClient()
    client.mode = "live"
    client.client = None
    env = client.complete("hello", make_session(), [])
    assert env.action == ActionEnum.ESCALATE
    assert env.citations == [Citation(source_id="warranty-safety-policy", locator="When to escalate")]


# ---------------------------------------------------------------------------
# Prompt-injection surface
# ---------------------------------------------------------------------------

def test_prior_user_turns_are_wrapped_and_context_header_marks_data():
    good = json.dumps({"response": "ok", "citations": [], "action": "instruct"})
    client = make_live_client([good], models=("model-a",))
    session = make_session(dialogue_window=[
        ChatMessage(role="user", content="earlier question"),
        ChatMessage(role="assistant", content="earlier answer"),
    ])
    chunk = make_chunk("led-reference", "N1 node LEDs", "| Pattern | Meaning | Customer action |")

    client.complete("current question", session, [chunk])

    messages = client.client.chat.completions.calls[0]["messages"]
    user_msgs = [m for m in messages if m["role"] == "user"]
    assert len(user_msgs) == 2
    for m in user_msgs:
        assert m["content"].startswith("<user_input>")
        assert m["content"].rstrip().endswith("</user_input>")
    assert "earlier question" in user_msgs[0]["content"]
    assert "current question" in user_msgs[1]["content"]

    assistant_msgs = [m for m in messages if m["role"] == "assistant"]
    assert assistant_msgs == [{"role": "assistant", "content": "earlier answer"}]

    context_msg = messages[1]["content"]
    assert context_msg.startswith("GROUNDED CONTEXT")
    assert "not instructions" in context_msg


# ---------------------------------------------------------------------------
# Record / replay
# ---------------------------------------------------------------------------

def test_replay_roundtrip_via_store_api(tmp_path):
    messages = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "<user_input>\nhello\n</user_input>"},
    ]
    envelope = ResponseEnvelope(
        response="Recorded answer.",
        citations=[Citation(source_id="led-reference", locator="N1 node LEDs")],
        action=ActionEnum.INSTRUCT,
    )

    path = replay.save_fixture(messages, envelope, "model-x", fixtures_dir=tmp_path)
    assert path.exists()

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["model"] == "model-x"
    assert payload["key"] == replay.fixture_key(messages)
    assert path.name == f"{payload['key']}.json"

    loaded = replay.load_fixture(messages, fixtures_dir=tmp_path)
    assert loaded == envelope


def test_replay_missing_fixture_raises_with_key_and_record_command(tmp_path):
    messages = [{"role": "user", "content": "never recorded"}]
    key = replay.fixture_key(messages)

    with pytest.raises(RuntimeError) as exc:
        replay.load_fixture(messages, fixtures_dir=tmp_path)

    text = str(exc.value)
    assert key in text
    assert "LLM_MODE=record" in text
    assert "eval/runner.py" in text


def test_fixture_key_is_deterministic_and_content_sensitive():
    a = [{"role": "user", "content": "one"}]
    assert replay.fixture_key(a) == replay.fixture_key([{"role": "user", "content": "one"}])
    assert replay.fixture_key(a) != replay.fixture_key([{"role": "user", "content": "two"}])


def test_record_mode_persists_and_replay_mode_replays_through_llmclient(monkeypatch, tmp_path):
    monkeypatch.setattr(replay, "FIXTURES_DIR", tmp_path)
    good = json.dumps({
        "response": "Check the blue WAN port.",
        "citations": [{"source_id": "led-reference", "locator": "R1 router LEDs"}],
        "action": "instruct",
    })
    recorder = make_live_client([good], models=("model-a",))
    recorder.mode = "record"

    recorded_env = recorder.complete("r1 flashing amber", make_session(), [])
    assert recorded_env.action == ActionEnum.INSTRUCT
    fixture_files = list(tmp_path.glob("*.json"))
    assert len(fixture_files) == 1
    assert json.loads(fixture_files[0].read_text(encoding="utf-8"))["model"] == "model-a"

    replayer = LLMClient()
    replayer.mode = "replay"
    replayer.client = None

    replayed_env = replayer.complete("r1 flashing amber", make_session(), [])
    assert replayed_env == recorded_env
