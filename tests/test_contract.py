import json
import pytest
from src.core.models import ResponseEnvelope, Citation, ActionEnum
from src.agent.orchestrator import OrbitMeshOrchestrator


def test_response_envelope_contract():
    env = ResponseEnvelope(
        response="Please check the Ethernet cable.",
        citations=[Citation(source_id="troubleshooting-guide", locator="Ethernet-connected N1")],
        action=ActionEnum.INSTRUCT
    )
    raw = env.model_dump_json()
    data = json.loads(raw)
    assert "response" in data and isinstance(data["response"], str)
    assert "action" in data and data["action"] in ["ask", "instruct", "resolved", "escalate"]
    assert "citations" in data and isinstance(data["citations"], list)
    assert data["citations"][0]["source_id"] == "troubleshooting-guide"
    assert data["citations"][0]["locator"] == "Ethernet-connected N1"


def test_orchestrator_turn_flow():
    orchestrator = OrbitMeshOrchestrator()
    resp = orchestrator.process_turn("test-contract-session", "Hello, my N1 node is showing solid amber.")
    assert resp.action in [ActionEnum.ASK, ActionEnum.INSTRUCT, ActionEnum.RESOLVED, ActionEnum.ESCALATE]
    assert len(resp.response) > 0
