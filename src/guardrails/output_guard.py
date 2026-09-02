from __future__ import annotations
import re
from typing import Optional, List, Dict, Set
from src.core.models import ResponseEnvelope, Citation, ActionEnum, DocumentChunk
from src.core.config import CORPUS_DIR
from src.core.logging import logger


class OutputGuardrail:
    _citation_index: Optional[Dict[str, Set[str]]] = None
    _corpus_sections: Optional[Dict[str, Dict[str, str]]] = None

    # Software surfaces that make "open the router ..." a UI action, not a hardware one.
    _SOFTWARE_SURFACE = r"(?:app|apps|application|settings?|console|dashboard|software|portal|page|interface|ui|admin)"

    # Physical-hazard actions. Word-boundary, context-aware: "open the router" only
    # counts when NOT followed by a software surface ("app", "settings", ...).
    HARDWARE_DANGER_PATTERNS: list[re.Pattern[str]] = [
        re.compile(
            r"\bopen(?:ing|ed)?\s+(?:up\s+)?(?:the\s+|my\s+|your\s+|a\s+|an\s+|this\s+|that\s+)?"
            r"(?:router|gateway|node|unit|device|adapter)\b"
            r"(?!(?:'s)?\s+" + _SOFTWARE_SURFACE + r"\b)",
            re.IGNORECASE,
        ),
        # "open (up) the [router] case/cover/housing" — physical enclosure, but not a
        # support case ("open a support case" stays allowed).
        re.compile(
            r"\bopen(?:ing|ed)?\s+(?:up\s+)?(?:the|its|my|your|this|that)\s+"
            r"(?:(?!support\b|ticket\b)\w+\s+){0,2}?(?:case|casing|cover|enclosure|housing|shell|chassis)\b",
            re.IGNORECASE,
        ),
        re.compile(r"\bunscrew\w*\b", re.IGNORECASE),
        re.compile(r"\bdisassembl\w+\b", re.IGNORECASE),
        re.compile(r"\btake\s+(?:it\s+|(?:the|my|your)\s+\w+\s+)?apart\b", re.IGNORECASE),
        re.compile(r"\bsolder\w*\b", re.IGNORECASE),
        re.compile(r"\brepair\s+(?:the\s+)?circuit\w*\b", re.IGNORECASE),
        re.compile(r"\bexposed?\s+wir\w+\b", re.IGNORECASE),
        re.compile(r"\binternal\s+capacitor\w*\b", re.IGNORECASE),
        re.compile(r"\b(?:pry|crack)\s+(?:it\s+)?open\b", re.IGNORECASE),
        re.compile(r"\bremove\s+(?:the\s+)?(?:cover|casing|housing|back\s*plate)\b", re.IGNORECASE),
    ]

    PHYSICAL_DAMAGE_PATTERNS: list[re.Pattern[str]] = [
        re.compile(r"\bsmoke\b|\bsmoking\b", re.IGNORECASE),
        re.compile(r"\bsparks?\b|\bsparking\b", re.IGNORECASE),
        re.compile(r"\bburn(?:ing|t)\s+smell\b|\bsmells?\s+(?:like\s+)?(?:burning|burnt|smoke)\b", re.IGNORECASE),
        re.compile(r"\bmelt(?:ed|ing)\b", re.IGNORECASE),
        re.compile(r"\bwater\s+damage\b|\bliquid\s+(?:spill\w*|exposure|damage)\b", re.IGNORECASE),
        re.compile(r"\bcracked\s+(?:housing|casing|case)\b", re.IGNORECASE),
        re.compile(r"\bcaught\s+fire\b|\bon\s+fire\b", re.IGNORECASE),
    ]

    UNSUPPORTED_FIRMWARE_PATTERNS: list[re.Pattern[str]] = [
        re.compile(r"\bopenwrt\b|\bdd-?wrt\b", re.IGNORECASE),
        re.compile(r"\b(?:custom|third[-\s]?party|unofficial)\s+firmware\b", re.IGNORECASE),
        re.compile(r"\bfirmware\s+(?:rollback|downgrade)\b", re.IGNORECASE),
        re.compile(r"\b(?:roll(?:\s|-)?back|downgrade)\s+(?:the\s+|my\s+)?firmware\b", re.IGNORECASE),
        re.compile(r"\b(?:re)?flash\s+(?:the\s+|my\s+|a\s+|new\s+|different\s+)?firmware\b", re.IGNORECASE),
    ]

    WARRANTY_CLAIM_PATTERNS: list[re.Pattern[str]] = [
        re.compile(r"\bwarranty\s+(?:replacement|claim)\b", re.IGNORECASE),
        re.compile(r"\bclaim\s+(?:\w+\s+){0,2}?under\s+(?:the\s+)?warranty\b", re.IGNORECASE),
        re.compile(r"\breplace\s+(?:it|this|my\s+\w+)\s+under\s+warranty\b", re.IGNORECASE),
    ]

    # Secret nouns the assistant must never request (warranty-safety-policy › When to
    # escalate). Applied to assistant OUTPUT.
    _SECRET_NOUNS = (
        r"(?:passwords?\b|passcodes?\b|passphrases?\b|"
        r"(?:wi[-\s]?fi|network|wpa2?|security|api|secret|private|admin|account|login|encryption|recovery)\s+keys?\b|"
        r"credit\s+cards?(?:\s+numbers?)?\b|payment\s+(?:info(?:rmation)?|details?)\b|"
        r"(?:full|entire|complete|whole)\s+serial(?:\s+numbers?)?\b)"
    )
    _FILLER_WORDS = r"(?:\w+[-']?\w*\s+)"
    SOLICITATION_PATTERNS: list[re.Pattern[str]] = [
        # "give/send/tell me your ... password/key/serial" with a few intervening words.
        re.compile(
            r"\b(?:enter|provide|type|give|send|share|tell|paste|input|supply|confirm|text|email)\s+"
            r"(?:me\s+|us\s+)?" + _FILLER_WORDS + r"{0,4}?" + _SECRET_NOUNS +
            r"(?!\s+(?:in|into|on)\s+(?:the|your)\s+(?:app|application|router|device|phone|laptop|browser|portal|settings))",
            re.IGNORECASE,
        ),
        # "what is / what's your password"
        re.compile(
            r"\bwhat(?:\s+is|'s)\s+(?:your|the)\s+" + _FILLER_WORDS + r"{0,3}?" + _SECRET_NOUNS,
            re.IGNORECASE,
        ),
        # "I need your Wi-Fi password"
        re.compile(
            r"\b(?:i|we)(?:'ll|\s+will)?\s+(?:also\s+|just\s+)?need\s+(?:your|the)\s+"
            + _FILLER_WORDS + r"{0,3}?" + _SECRET_NOUNS,
            re.IGNORECASE,
        ),
        # "may/can/could I have your password"
        re.compile(
            r"\b(?:may|can|could)\s+i\s+(?:please\s+)?(?:have|get)\s+(?:your|the)\s+"
            + _FILLER_WORDS + r"{0,3}?" + _SECRET_NOUNS,
            re.IGNORECASE,
        ),
    ]
    # A negation shortly before the match means the text is advice ("Never share your
    # password"), not a request for it.
    _NEGATION_BEFORE = re.compile(
        r"\b(?:never|don'?t|do\s+not|won'?t|will\s+not|shouldn'?t|should\s+not|no\s+need\s+to|not|without|avoid)\b",
        re.IGNORECASE,
    )

    # Factory-reset REQUEST intent in the user message. Anchored on present-tense
    # request forms so past-tense reports ("I already did a factory reset") and
    # negations ("I don't want to factory reset") do not fire.
    _RESET_NOUN = r"(?:factory[-\s]+reset|factory\s+restore|full[-\s]+reset|hard[-\s]+reset)"
    RESET_REQUEST_PATTERNS: list[re.Pattern[str]] = [
        re.compile(
            r"\b(?:how\s+do\s+i|how\s+can\s+i|how\s+to|i\s+(?:want|need|would\s+like)\s+(?:you\s+to|to)|i'?d\s+like\s+to|"
            r"should\s+i|can\s+i|could\s+i|may\s+i|going\s+to|about\s+to|let'?s|please)\s+"
            r"(?:just\s+|go\s+ahead\s+and\s+)?(?:do\s+(?:a|the)\s+|perform\s+(?:a|the)\s+|run\s+(?:a|the)\s+|try\s+(?:a|the)\s+|start\s+(?:a|the)\s+)?"
            r"(?:" + _RESET_NOUN + r"|reset)\b",
            re.IGNORECASE,
        ),
        # Present-tense "do/perform a factory reset" anywhere ("did a factory reset" does not match).
        re.compile(
            r"\b(?:do|perform|run|start|initiate|trigger)\s+(?:a|the)\s+(?:full\s+)?" + _RESET_NOUN + r"\b",
            re.IGNORECASE,
        ),
        # Imperative at the start of the message or a sentence: "reset it / reset everything".
        re.compile(
            r"(?:^|[.!?]\s+)(?:please\s+|just\s+)?(?:factory[-\s]+)?reset\s+"
            r"(?:it|everything|(?:the|my|this|that)\s+(?:whole\s+)?(?:router|gateway|node|unit|device|network|system|mesh))\b",
            re.IGNORECASE,
        ),
        re.compile(r"\breset\s+(?:it\s+)?to\s+factory(?:\s+(?:defaults?|settings))?\b", re.IGNORECASE),
        re.compile(r"\bfull\s+wipe\b|\bwipe\s+everything\b|\berase\s+all\s+configuration\b", re.IGNORECASE),
    ]

    # The assistant's proposed response actually PROPOSES a factory reset (not merely
    # mentions one).
    RESET_RESPONSE_PATTERNS: list[re.Pattern[str]] = [
        re.compile(r"\b(?:do|perform|run|start|initiate|trigger)\s+(?:a|the)\s+(?:full\s+)?" + _RESET_NOUN + r"\b", re.IGNORECASE),
        re.compile(r"\b(?:recommend|suggest)\s+(?:a\s+|the\s+)?" + _RESET_NOUN + r"\b", re.IGNORECASE),
        re.compile(r"\b" + _RESET_NOUN + r"\s+(?:the|your|it|everything|all)\b", re.IGNORECASE),
        re.compile(r"\bnext\s+step\s+is\s+(?:a\s+|the\s+)?" + _RESET_NOUN + r"\b", re.IGNORECASE),
        re.compile(r"\bwe(?:'ll|\s+will)\s+(?:need\s+to\s+)?" + _RESET_NOUN + r"\b", re.IGNORECASE),
        re.compile(r"\breset\s+to\s+factory(?:\s+(?:defaults?|settings))?\b", re.IGNORECASE),
        re.compile(r"\bpinhole\s+reset\b", re.IGNORECASE),
        re.compile(r"\bhold(?:ing)?\s+(?:the\s+)?reset(?:\s+button)?\s+for\s+(?:at\s+least\s+)?1[0-9]\b", re.IGNORECASE),
        re.compile(r"\berase\s+all\s+(?:local\s+)?configuration\b", re.IGNORECASE),
        re.compile(r"\bfull\s+wipe\b", re.IGNORECASE),
    ]

    # User explicitly insists after being pointed at the documented path.
    RESET_INSISTENCE_PATTERN = re.compile(
        r"\b(?:anyway|regardless|i\s+insist|i\s+understand\s+the\s+risks?|"
        r"just\s+(?:do\s+(?:it|the\s+reset)|reset\s+it)|"
        r"still\s+want\s+(?:to\s+|the\s+)?(?:factory[-\s]+)?reset|"
        r"already\s+(?:tried|done|completed|followed)\b[^.?!]{0,60}?\b(?:steps?|guide|troubleshooting|everything|path)|"
        r"tried\s+everything|nothing\s+(?:else\s+)?(?:worked|works|helped|helps))\b",
        re.IGNORECASE,
    )

    @classmethod
    def get_corpus_sections(cls) -> Dict[str, Dict[str, str]]:
        if cls._corpus_sections is None:
            sections: Dict[str, Dict[str, str]] = {}
            if CORPUS_DIR.exists():
                header_re = re.compile(r"^(#{1,6})\s+(.*)$")
                for f in CORPUS_DIR.glob("*.md"):
                    doc_id = f.stem
                    doc_sections: Dict[str, str] = {}
                    try:
                        file_content = f.read_text(encoding="utf-8")
                        current_header = "Intro"
                        current_lines: List[str] = []
                        for line in file_content.splitlines():
                            m = header_re.match(line)
                            if m:
                                if current_lines:
                                    doc_sections[current_header] = "\n".join(current_lines).strip()
                                current_header = m.group(2).strip()
                                current_lines = []
                            else:
                                current_lines.append(line)
                        if current_lines:
                            doc_sections[current_header] = "\n".join(current_lines).strip()
                        sections[doc_id] = doc_sections
                    except Exception as e:
                        logger.error(f"Error loading sections for {doc_id}: {e}")
            cls._corpus_sections = sections
        return cls._corpus_sections

    # Retrieve at runtime from corpus
    @classmethod
    def get_section_text(cls, doc_id: str, locator: str) -> str:
        sections = cls.get_corpus_sections()
        doc_secs = sections.get(doc_id, {})
        if locator in doc_secs:
            return doc_secs[locator]
        for sec_name, text in doc_secs.items():
            if locator.lower() in sec_name.lower() or sec_name.lower() in locator.lower():
                return text
        return ""

    @classmethod
    def get_corpus_citation_index(cls) -> Dict[str, Set[str]]:
        if cls._citation_index is None:
            index: Dict[str, Set[str]] = {}
            if CORPUS_DIR.exists():
                header_re = re.compile(r"^(#{1,6})\s+(.*)$", re.MULTILINE)
                for f in CORPUS_DIR.glob("*.md"):
                    doc_id = f.stem
                    try:
                        file_content = f.read_text(encoding="utf-8")
                        headers = {m.group(2).strip() for m in header_re.finditer(file_content)}
                        index[doc_id] = headers
                    except Exception:
                        pass
            cls._citation_index = index
        return cls._citation_index

    # ------------------------------------------------------------------
    # Corpus-driven copy helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _first_match(patterns: list[re.Pattern[str]], text: str) -> str | None:
        for pattern in patterns:
            m = pattern.search(text)
            if m:
                return m.group(0)
        return None

    @classmethod
    def _sentence_containing(cls, text: str, needle: str, fallback: str) -> str:
        """Return the corpus sentence containing `needle`, or a policy-compliant fallback."""
        if text:
            for sentence in re.split(r"(?<=[.!?])\s+", text):
                if needle.lower() in sentence.lower():
                    return sentence.strip()
        return fallback

    @classmethod
    def _support_channel_direction(cls) -> str:
        """Escalation direction per warranty-safety-policy › Escalation message."""
        esc_text = cls.get_section_text("warranty-safety-policy", "Escalation message")
        m = re.search(r"use\s+the\s+(support\s+channel[^.,;]*)", esc_text, re.IGNORECASE)
        channel = m.group(1).strip() if m else "support channel in the OrbitMesh app"
        return f"Please continue with OrbitMesh Support via the {channel}."

    # Never instruct a customer to open or repair powered hardware
    # Warranty and undocumented procedures
    @classmethod
    def check_hardware_safety(cls, user_message: str, proposed_response: str) -> Optional[ResponseEnvelope]:
        msg = user_message or ""
        resp = proposed_response or ""
        direction = cls._support_channel_direction()

        damage_term = cls._first_match(cls.PHYSICAL_DAMAGE_PATTERNS, msg)
        if damage_term:
            logger.warning(f"Hardware hazard detected: {damage_term}. Escalating.")
            safety_sentence = cls._sentence_containing(
                cls.get_section_text("warranty-safety-policy", "Safety"),
                "Disconnect power",
                "Disconnect power and stop troubleshooting if a unit is unusually hot, emits smoke "
                "or a burnt smell, has liquid exposure, or shows damaged casing or cabling.",
            )
            provide_sentence = cls._sentence_containing(
                cls.get_section_text("warranty-safety-policy", "When to escalate"),
                "Provide the model",
                "Provide the model, firmware version, approximate purchase date, LED/error state, "
                "topology, and steps already attempted.",
            )
            return ResponseEnvelope(
                response=(
                    f"You reported a possible safety condition ({damage_term}). {safety_sentence} "
                    f"{direction} {provide_sentence}"
                ),
                citations=[
                    Citation(source_id="warranty-safety-policy", locator="Safety"),
                    Citation(source_id="warranty-safety-policy", locator="Escalation message"),
                ],
                action=ActionEnum.ESCALATE,
            )

        danger_term = cls._first_match(cls.HARDWARE_DANGER_PATTERNS, resp) or cls._first_match(
            cls.HARDWARE_DANGER_PATTERNS, msg
        )
        if danger_term:
            logger.error(f"Dangerous hardware instruction or request intercepted: {danger_term}")
            safety_text = cls.get_section_text("warranty-safety-policy", "Safety")
            must_not_open = cls._sentence_containing(
                safety_text, "must not open",
                "Customers must not open an R1, N1, or power adapter.",
            )
            no_parts = cls._sentence_containing(
                safety_text, "customer-serviceable",
                "There are no customer-serviceable internal parts.",
            )
            return ResponseEnvelope(
                response=(
                    f"I can't help with opening or repairing OrbitMesh hardware. {must_not_open} "
                    f"{no_parts} {direction}"
                ),
                citations=[
                    Citation(source_id="warranty-safety-policy", locator="Safety"),
                    Citation(source_id="warranty-safety-policy", locator="Escalation message"),
                ],
                action=ActionEnum.ESCALATE,
            )

        firmware_term = cls._first_match(cls.UNSUPPORTED_FIRMWARE_PATTERNS, msg) or cls._first_match(
            cls.UNSUPPORTED_FIRMWARE_PATTERNS, resp
        )
        if firmware_term:
            logger.info("Unsupported custom firmware flashing or rollback attempt detected. Escalating.")
            rec_sentence = cls._sentence_containing(
                cls.get_section_text("reset-recovery-guide", "Recovery and escalation"),
                "no customer-supported",
                "There is no customer-supported firmware rollback, case opening, internal battery "
                "disconnection, or USB recovery procedure.",
            )
            return ResponseEnvelope(
                response=f"{rec_sentence} {direction}",
                citations=[
                    Citation(source_id="reset-recovery-guide", locator="Recovery and escalation"),
                    Citation(source_id="warranty-safety-policy", locator="Escalation message"),
                ],
                action=ActionEnum.ESCALATE,
            )

        warranty_term = cls._first_match(cls.WARRANTY_CLAIM_PATTERNS, msg)
        if warranty_term:
            logger.info("Warranty claim detected. Escalating per policy.")
            warranty_text = cls.get_section_text("warranty-safety-policy", "Limited warranty")
            coverage_sentence = cls._sentence_containing(
                warranty_text, "do not establish coverage",
                "Symptoms, LEDs, purchase dates, and chat conversations do not establish coverage.",
            )
            eligibility_sentence = cls._sentence_containing(
                warranty_text, "Support determines eligibility",
                "Support determines eligibility after verifying purchase evidence, region, serial "
                "number, condition, and exclusions.",
            )
            return ResponseEnvelope(
                response=f"{coverage_sentence} {eligibility_sentence} {direction}",
                citations=[
                    Citation(source_id="warranty-safety-policy", locator="Limited warranty"),
                    Citation(source_id="warranty-safety-policy", locator="Escalation message"),
                ],
                action=ActionEnum.ESCALATE,
            )

        return None

    # Intercept password, key, or sensitive info solicitation in proposed output.
    # The rule (warranty-safety-policy › When to escalate): the assistant must never
    # REQUEST secrets; advice about secrets ("never share your password") passes.
    @classmethod
    def _find_solicitation(cls, text: str) -> re.Match[str] | None:
        for pattern in cls.SOLICITATION_PATTERNS:
            for m in pattern.finditer(text):
                window = text[max(0, m.start() - 40):m.start()]
                if cls._NEGATION_BEFORE.search(window):
                    continue
                return m
        return None

    @classmethod
    def check_sensitive_info_solicitation(cls, proposed_envelope: ResponseEnvelope) -> ResponseEnvelope:
        if cls._find_solicitation(proposed_envelope.response):
            logger.warning("Secret or sensitive data solicitation detected in output. Intercepting.")
            policy_text = cls.get_section_text("warranty-safety-policy", "When to escalate")
            never_sentence = cls._sentence_containing(
                policy_text, "Never request",
                "Never request Wi-Fi passwords, account passwords, API keys, payment details, "
                "or a full serial number.",
            )
            share_sentence = cls._sentence_containing(
                policy_text, "final four characters",
                "Share only the final four characters of the serial number in chat.",
            )
            return ResponseEnvelope(
                response=(
                    f"I don't require any credentials to continue. OrbitMesh policy: {never_sentence} "
                    f"{share_sentence} We can keep troubleshooting without that information — "
                    f"could you describe what the device is doing right now?"
                ),
                citations=[Citation(source_id="warranty-safety-policy", locator="When to escalate")],
                action=ActionEnum.ASK,
            )
        return proposed_envelope

    # ------------------------------------------------------------------
    # Factory reset
    # ------------------------------------------------------------------

    @classmethod
    def _documented_path_first_envelope(cls) -> ResponseEnvelope:
        """Corpus precondition (reset-recovery-guide): factory reset is a last resort.

        Point the customer at the least destructive documented step before any
        warning + confirmation flow.
        """
        reset_text = cls.get_section_text("reset-recovery-guide", "Factory reset — erases configuration")
        last_resort = cls._sentence_containing(
            reset_text, "last resort",
            "Factory reset is a last resort after the applicable documented path has failed.",
        )
        restart_text = cls.get_section_text("reset-recovery-guide", "Restart — no configuration loss")
        restart_step = (
            restart_text.split("\n\n")[0].strip()
            if restart_text
            else (
                "Disconnect the unit's power cable, wait 10 seconds, and reconnect it. A restart "
                "retains the network name, password, device assignments, and settings."
            )
        )
        return ResponseEnvelope(
            response=(
                f"{last_resort} Before erasing your configuration, let's try the least destructive "
                f"documented step first. {restart_step} If the documented troubleshooting for your "
                f"issue has already failed and you still want a factory reset, tell me and I will "
                f"walk you through the warning and confirmation."
            ),
            citations=[
                Citation(source_id="reset-recovery-guide", locator="Factory reset — erases configuration"),
                Citation(source_id="reset-recovery-guide", locator="Restart — no configuration loss"),
            ],
            action=ActionEnum.ASK,
        )

    @classmethod
    def _reset_warning_envelope(cls) -> ResponseEnvelope:
        reset_text = cls.get_section_text("reset-recovery-guide", "Factory reset — erases configuration")
        first_para = (
            reset_text.split("\n\n")[0].strip()
            if reset_text
            else (
                "A factory reset erases the network name and password, node pairings, guest networks, "
                "parental controls, reservations, and all other local configuration. Every node must "
                "be paired again."
            )
        )
        warning_msg = (
            f"Warning: A factory reset will permanently erase all configuration. {first_para} "
            f"Please confirm that you are able to recreate the network and reconnect your devices. "
            f"Would you like to proceed with the factory reset? (Please reply Yes or No)"
        )
        return ResponseEnvelope(
            response=warning_msg,
            citations=[Citation(source_id="reset-recovery-guide", locator="Factory reset — erases configuration")],
            action=ActionEnum.ASK,
        )

    # Warn before factory reset
    @classmethod
    def check_factory_reset_safety(
        cls,
        user_message: str,
        proposed_envelope: ResponseEnvelope,
        confirmed_reset: bool,
        attempted_steps: list[str] | None = None,
    ) -> ResponseEnvelope:
        if confirmed_reset:
            return proposed_envelope

        user_requests_reset = any(p.search(user_message) for p in cls.RESET_REQUEST_PATTERNS)
        response_proposes_reset = any(
            p.search(proposed_envelope.response) for p in cls.RESET_RESPONSE_PATTERNS
        )
        if not (user_requests_reset or response_proposes_reset):
            return proposed_envelope

        # Corpus precondition (reset-recovery-guide › Factory reset — erases
        # configuration): "a last resort after the applicable documented path has
        # failed". When the caller reports that no documented step has been attempted
        # ([]), point to the documented path first instead of warn+confirm. The
        # orchestrator owns the pending_confirmation state for the insistence flow;
        # attempted_steps=None (default) preserves the previous warn+confirm behavior.
        user_insists = bool(cls.RESET_INSISTENCE_PATTERN.search(user_message))
        if attempted_steps is not None and not attempted_steps and not user_insists:
            logger.info("Factory reset requested with no documented steps attempted. Deflecting to documented path.")
            return cls._documented_path_first_envelope()

        logger.info("Factory reset proposed or requested without confirmation. Intercepting with warning.")
        return cls._reset_warning_envelope()

    # If document does not exist, no source_id, try to repair, if not drop it
    # If document exist, but locator is missing, try to validate and repair, if not use the retrieved_chunks, else drop it
    # If no citations, use the top retrieved chunk
    # Might have an issue with eval since it returns the retrieved chunk due to fallback after failing repairs
    @classmethod
    def validate_and_repair_citations(
        cls,
        citations: List[Citation],
        retrieved_chunks: Optional[List[DocumentChunk]] = None
    ) -> List[Citation]:
        index = cls.get_corpus_citation_index() # Get index in memory map
        valid_citations: List[Citation] = []
        seen = set()

        for c in citations:
            src_id = c.source_id.strip() if c.source_id else ""
            locator = c.locator.strip() if c.locator else ""

            if not src_id:
                continue

            if src_id not in index:
                matched_src = next((k for k in index if k.lower() == src_id.lower() or k.lower() in src_id.lower()), None)
                if matched_src:
                    src_id = matched_src
                else:
                    logger.warning(f"Dropping ungrounded citation source: {src_id}")
                    continue

            valid_headers = index[src_id]
            if locator in valid_headers:
                pair = (src_id, locator)
                if pair not in seen:
                    seen.add(pair)
                    valid_citations.append(Citation(source_id=src_id, locator=locator))
                continue

            repaired_locator = None
            loc_lower = locator.lower()
            repaired_locator = next((h for h in valid_headers if h.lower() == loc_lower), None)

            if not repaired_locator:
                candidates = [h for h in valid_headers if loc_lower in h.lower() or h.lower() in loc_lower]
                if candidates:
                    repaired_locator = min(candidates, key=lambda h: abs(len(h) - len(locator)))

            if repaired_locator:
                pair = (src_id, repaired_locator)
                if pair not in seen:
                    seen.add(pair)
                    valid_citations.append(Citation(source_id=src_id, locator=repaired_locator))
            else:
                if retrieved_chunks:
                    chunk_match = next((chk for chk in retrieved_chunks if chk.metadata.source_id == src_id), None)
                    if chunk_match and chunk_match.metadata.locator in valid_headers:
                        pair = (src_id, chunk_match.metadata.locator)
                        if pair not in seen:
                            seen.add(pair)
                            valid_citations.append(Citation(source_id=src_id, locator=chunk_match.metadata.locator))
                            continue
                logger.warning(f"Dropping unresolvable locator '{locator}' for source '{src_id}'")

        if not valid_citations and retrieved_chunks:
            top = retrieved_chunks[0]
            if top.metadata.source_id in index and top.metadata.locator in index[top.metadata.source_id]:
                valid_citations.append(Citation(source_id=top.metadata.source_id, locator=top.metadata.locator))

        return valid_citations
