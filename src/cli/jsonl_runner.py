from __future__ import annotations
import json
import sys
from src.agent.orchestrator import OrbitMeshOrchestrator
from src.core.logging import logger


def run_jsonl_stream():
    orchestrator = OrbitMeshOrchestrator()
    logger.info("OrbitMesh JSONL streaming runner ready on stdin.")

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
            session_id = req.get("session_id", "default-session")
            message = req.get("message", "")

            envelope = orchestrator.process_turn(session_id, message)
            output_dict = envelope.model_dump()

            sys.stdout.write(json.dumps(output_dict) + "\n")
            sys.stdout.flush()
        except Exception as e:
            logger.error(f"Error processing JSON line: {e}")
            fallback_dict = {
                "response": "An error occurred while processing your request. Escalating to support.",
                "citations": [],
                "action": "escalate"
            }
            sys.stdout.write(json.dumps(fallback_dict) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    run_jsonl_stream()
