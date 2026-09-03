from __future__ import annotations
import re
from typing import Optional

from src.core.models import ResponseEnvelope, ActionEnum, Citation
from src.guardrails.input_guard import InputGuardrail
from src.guardrails.output_guard import OutputGuardrail
from src.state.session import SessionStateManager, SessionManager
from src.rag.retriever import HybridRetriever
from src.rag.llm import LLMClient


# Main orchestrator for end to end pipeline
class OrbitMeshOrchestrator:
    def __init__(self, retriever: Optional[HybridRetriever] = None, llm: Optional[LLMClient] = None):
        self.retriever = retriever or HybridRetriever()
        self.llm = llm or LLMClient()
        self.session_manager = SessionStateManager
        self.last_retrieved_chunks = []
        self.last_raw_envelope: Optional[ResponseEnvelope] = None

    def process_turn(self, session_id: str, user_message: str) -> ResponseEnvelope:
        self.last_retrieved_chunks = []
        self.last_raw_envelope = None

        # 1. Get existing or create new sess
        session = self.session_manager.get_or_create(session_id)
        session.turns_count += 1

        # 2. Input Guardrail check
        isolated_msg, is_safe, clean_msg = InputGuardrail.sanitize_and_inspect(user_message)
        msg_lower = clean_msg.lower().strip()

        # 3. Do Hardware hazard check
        hazard_envelope = OutputGuardrail.check_hardware_safety(clean_msg, "")
        if hazard_envelope:
            session.is_escalated = True
            self.session_manager.record_turn(session, clean_msg, hazard_envelope.response, step_executed="hazard_escalation")
            return hazard_envelope

        # 4. Prompt injection containment
        if not is_safe:
            injection_envelope = ResponseEnvelope(
                response="I can only assist with official OrbitMesh device troubleshooting and network configuration. How can I help with your OrbitMesh system?",
                citations=[],
                action=ActionEnum.ASK
            )
            self.session_manager.record_turn(session, clean_msg, injection_envelope.response)
            return injection_envelope

        # 5. Model identification
        # Update model identification slot if detected via word-boundary token matching
        if re.search(r"\b(r5\s*pro|n5\s*pro|pro\s+gateway|pro\s+node|orbitmesh\s+pro)\b", msg_lower):
            session.identified_model = "OrbitMesh Pro"
        elif re.search(r"\b(r1|r1\s*router|main\s*router)\b", msg_lower):
            session.identified_model = "OrbitMesh R1"
        elif re.search(r"\b(n1|n1\s*node|satellite\s*node|satellite)\b", msg_lower):
            session.identified_model = "OrbitMesh N1"

        is_yes = bool(re.search(r"\b(yes|yep|yeah|proceed|confirm|confirmed|sure|ok|okay|go\s+ahead|do\s+it)\b", msg_lower))
        is_no = bool(re.search(r"\b(no|cancel|stop|abort|don'?t|do\s+not|nevermind|never\s+mind|skip)\b", msg_lower))

        # 6. Check Factory reset confirmation only fires when a prior turn set pending_confirmation
        if session.pending_confirmation == "factory_reset":
            if is_no and not is_yes:
                session.pending_confirmation = None
                restart_text = OutputGuardrail.get_section_text("reset-recovery-guide", "Restart — no configuration loss")
                first_sent = restart_text.split(". ")[0] if restart_text else "Disconnect the unit's power cable, wait 10 seconds, and reconnect it."
                alt_resp = f"Understood, skipping factory reset. As a non-destructive alternative: {first_sent} Would you like to try this?"
                citation = Citation(source_id="reset-recovery-guide", locator="Restart — no configuration loss")
                envelope = ResponseEnvelope(response=alt_resp, citations=[citation], action=ActionEnum.ASK)
                self.session_manager.record_turn(session, clean_msg, envelope.response)
                return envelope
            elif is_yes and not is_no:
                session.pending_confirmation = None
                session.confirmed_facts["factory_reset_confirmed"] = True
                model = session.identified_model or "N1"
                if "pro" in model.lower():
                    citation = Citation(source_id="pro-quick-start-guide", locator="Factory reset")
                    pro_reset = OutputGuardrail.get_section_text("pro-quick-start-guide", "Factory reset")
                    step = pro_reset if pro_reset else "Hold the recessed reset pin for 10 seconds until the LED flashes blue, then release. The node returns to an unclaimed state."
                else:
                    citation = Citation(source_id="reset-recovery-guide", locator="Factory reset — erases configuration")
                    std_reset = OutputGuardrail.get_section_text("reset-recovery-guide", "Factory reset — erases configuration")
                    paras = [p for p in std_reset.split("\n\n") if "only after confirmation" in p.lower()]
                    step = paras[0] if paras else "With the unit powered, hold reset for at least 15 seconds until the LED flashes red, then release. Keep power connected while it recovers."
                envelope = ResponseEnvelope(response=step, citations=[citation], action=ActionEnum.INSTRUCT)
                self.session_manager.record_turn(session, clean_msg, envelope.response, step_executed="factory_reset")
                return envelope
            elif any(w in msg_lower for w in ["anything else", "try before", "alternative", "before wiping", "before resetting"]):
                session.pending_confirmation = None
                alt_resp = "Before performing a factory reset, try power cycling the device: disconnect power for 10 seconds and reconnect. If it is an N1 node, you may also attempt a pairing reset by holding the reset button for 5–7 seconds until the LED pulses blue."
                citation = Citation(source_id="reset-recovery-guide", locator="Restart — no configuration loss")
                envelope = ResponseEnvelope(response=alt_resp, citations=[citation], action=ActionEnum.ASK)
                self.session_manager.record_turn(session, clean_msg, envelope.response)
                return envelope
            else:
                session.pending_confirmation = None

        # 7. Start RAG Retrieval based on model
        model_str = session.identified_model or ""
        product_line_filter = "Pro" if "pro" in model_str.lower() else ("Standard" if any(x in model_str.lower() for x in ["r1", "n1"]) else None)

        self.last_retrieved_chunks = []
        retrieved_chunks = self.retriever.retrieve(
            query=clean_msg,
            top_k=4,
            product_line=product_line_filter,
            include_archived=("archive" in msg_lower or "superseded" in msg_lower)
        )

        self.last_retrieved_chunks = retrieved_chunks
        # 8. Package the output
        proposed_envelope = self.llm.complete(clean_msg, session, retrieved_chunks)
        self.last_raw_envelope = proposed_envelope

        # 9. Check for Output Guardrail
        hardware_check = OutputGuardrail.check_hardware_safety(clean_msg, proposed_envelope.response)
        if hardware_check:
            final_envelope = hardware_check
        else:
            confirmed_reset = session.confirmed_facts.get("factory_reset_confirmed", False)
            final_envelope = OutputGuardrail.check_factory_reset_safety(clean_msg, proposed_envelope, confirmed_reset)
            if final_envelope.response.startswith("Warning: A factory reset") or (
                any(w in clean_msg.lower() for w in ["factory reset", "full reset", "reset everything"]) and final_envelope.action == ActionEnum.ASK
            ):
                session.pending_confirmation = "factory_reset"
            
            # Sensitive info solicitation check
            final_envelope = OutputGuardrail.check_sensitive_info_solicitation(final_envelope)

        # 10. Validate citations against grounded corpus index
        final_envelope.citations = OutputGuardrail.validate_and_repair_citations(
            final_envelope.citations,
            retrieved_chunks
        )
    
        # 11. Update the session with the final response
        step_executed = None
        if final_envelope.action == ActionEnum.INSTRUCT:
            resp_l = final_envelope.response.lower()
            if "factory reset" in resp_l or "hold the reset" in resp_l or "reset pin" in resp_l:
                step_executed = "factory_reset"
            elif "ethernet" in resp_l or "cable" in resp_l:
                step_executed = "cable_checked"
            elif "power cycle" in resp_l or "unplug" in resp_l or "restart" in resp_l:
                step_executed = "power_cycled"
            elif "distance" in resp_l or "closer" in resp_l:
                step_executed = "distance_checked"
            elif "channel" in resp_l or "app" in resp_l:
                step_executed = "channel_optimized"
            else:
                step_executed = "instruction_step"

        if final_envelope.action == ActionEnum.RESOLVED:
            session.is_resolved = True
        elif final_envelope.action == ActionEnum.ESCALATE:
            session.is_escalated = True

        self.session_manager.record_turn(session, clean_msg, final_envelope.response, step_executed=step_executed)
        return final_envelope