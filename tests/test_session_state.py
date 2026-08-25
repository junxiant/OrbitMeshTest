import pytest
from pathlib import Path
from src.core.models import SessionState, ChatMessage, ConfirmationType, ActionEnum
from src.state.session import SessionStateManager
from src.agent.orchestrator import OrbitMeshOrchestrator


@pytest.fixture(autouse=True)
def isolated_test_db(tmp_path, monkeypatch):
    test_db = tmp_path / "test_sessions.db"
    monkeypatch.setattr(SessionStateManager, "_db_path", test_db)
    monkeypatch.setattr(SessionStateManager, "_initialized", False)
    SessionStateManager._init_db_once()
    yield
    SessionStateManager.reset_all()


def test_session_continuity():
    session_id = "test-continuity-1"
    s1 = SessionStateManager.get_or_create(session_id)
    assert s1.session_id == session_id
    assert s1.identified_model is None
    assert s1.attempted_steps == []

    SessionStateManager.update_slots(session_id, identified_model="OrbitMesh N1")
    SessionStateManager.add_turn(session_id, "My LED is amber", "Move the node closer", step_executed="distance_checked")

    s2 = SessionStateManager.get_or_create(session_id)
    assert s2.identified_model == "OrbitMesh N1"
    assert s2.attempted_steps == ["distance_checked"]
    assert len(s2.dialogue_window) == 2


def test_sliding_window_pruning():
    session_id = "test-window-1"
    max_turns = 4

    for i in range(10):
        SessionStateManager.add_turn(
            session_id=session_id,
            user_message=f"User message {i+1}",
            assistant_response=f"Assistant response {i+1}",
            step_executed=f"step_{i+1}",
            max_window_turns=max_turns
        )

    state = SessionStateManager.get_or_create(session_id)
    assert len(state.dialogue_window) == max_turns * 2  # 8 messages
    assert state.dialogue_window[0].content == "User message 7"
    assert state.dialogue_window[-1].content == "Assistant response 10"
    assert len(state.attempted_steps) == 10
    assert state.attempted_steps == [f"step_{i+1}" for i in range(10)]


def test_step_deduplication():
    session_id = "test-dedup-1"
    SessionStateManager.add_turn(session_id, "msg 1", "resp 1", step_executed="power_cycle")
    SessionStateManager.add_turn(session_id, "msg 2", "resp 2", step_executed="power_cycle")
    SessionStateManager.add_turn(session_id, "msg 3", "resp 3", step_executed="cable_check")
    SessionStateManager.add_turn(session_id, "msg 4", "resp 4", step_executed="power_cycle")

    state = SessionStateManager.get_or_create(session_id)
    assert state.attempted_steps == ["power_cycle", "cable_check"]


def test_reset_state_machine_transition():
    orchestrator = OrbitMeshOrchestrator()
    session_id = "test-reset-sm-1"

    state = SessionStateManager.get_or_create(session_id)
    assert state.pending_confirmation is None

    # Step 1: User asks for factory reset -> Orchestrator intercepts and sets pending_confirmation = factory_reset
    resp1 = orchestrator.process_turn(session_id, "I want to do a factory reset on my N1 node")
    assert resp1.action == ActionEnum.ASK
    assert "Warning: A factory reset" in resp1.response

    state1 = SessionStateManager.get_or_create(session_id)
    assert state1.pending_confirmation == "factory_reset"

    # Step 2: User confirms -> Orchestrator clears pending_confirmation and gives instructions
    resp2 = orchestrator.process_turn(session_id, "Yes, proceed with reset")
    assert resp2.action == ActionEnum.INSTRUCT
    assert "reset" in resp2.response.lower()

    state2 = SessionStateManager.get_or_create(session_id)
    assert state2.pending_confirmation is None
    assert "factory_reset" in state2.attempted_steps


def test_prompt_context_builder():
    session_id = "test-ctx-1"
    SessionStateManager.update_slots(session_id, identified_model="OrbitMesh Pro", pending_confirmation="factory_reset")
    SessionStateManager.add_turn(session_id, "Help with setup", "Connect WAN port", step_executed="wan_check")

    ctx = SessionStateManager.build_prompt_context(session_id)
    assert ctx["identified_model"] == "OrbitMesh Pro"
    assert ctx["attempted_steps"] == ["wan_check"]
    assert ctx["pending_confirmation"] == "factory_reset"
    assert len(ctx["recent_messages"]) == 2
    assert ctx["recent_messages"][0]["role"] == "user"
    assert ctx["recent_messages"][0]["content"] == "Help with setup"


def test_turn_count_and_lifecycle_flags_persistence():
    orchestrator = OrbitMeshOrchestrator()
    session_id = "test-flags-persistence"

    r1 = orchestrator.process_turn(session_id, "My R1 router is not connecting to modem")
    s1 = SessionStateManager.get_or_create(session_id)
    assert s1.turns_count == 1
    assert s1.identified_model == "OrbitMesh R1"
    assert s1.is_resolved is False

    r2 = orchestrator.process_turn(session_id, "That fixed it, thank you!")
    s2 = SessionStateManager.get_or_create(session_id)
    assert s2.turns_count == 2
    assert s2.is_resolved is True
    assert len(s2.dialogue_window) == 4
