from __future__ import annotations

import re

from src.core.logging import logger


# Safety and Guardrails as per requirements
class InputGuardrail:
    # Credential disclosure requires an explicit separator (is / : / =) between the
    # credential keyword and the secret candidate. Bare "password doesn't ..." style
    # continuations are conversation, not disclosure.
    PASSWORD_PATTERN = re.compile(
        r"\b(?:password|passcode|passphrase|wifi\s*key|network\s+key|wpa2?(?:\s+(?:key|passphrase))?|pwd|secret)"
        r"(?:\s+is\s+|\s*[:=]\s*)([A-Za-z0-9!@#$%^&*()_+=\-]{4,})",
        re.IGNORECASE,
    )
    # Common English continuations after "password is ..." that are chatter, not secrets.
    _COMMON_CONTINUATIONS = frozenset({
        "wrong", "incorrect", "invalid", "correct", "working", "changed", "missing",
        "different", "still", "also", "already", "probably", "definitely", "there",
        "here", "what", "that", "this", "case", "sensitive", "blank", "empty",
        "hidden", "visible", "forgotten", "unknown", "broken", "expired", "right",
        "fine", "okay", "gone", "same", "secure", "insecure", "weak", "strong",
        "safe", "long", "short", "required", "needed", "does", "doesn", "isn",
        "wasn", "didn", "don", "won", "shouldn", "couldn", "wouldn", "really",
        "very", "actually", "always", "never", "sometimes",
    })

    # For API or any 'secrets'
    API_KEY_PATTERN = re.compile(r"(?:sk-[A-Za-z0-9]{20,}|Bearer\s+[A-Za-z0-9._-]{20,})", re.IGNORECASE)

    # Full serial number disclosure (policy allows only the last 4 characters).
    # Requires a separator and a serial-shaped candidate (must contain a digit).
    SERIAL_PATTERN = re.compile(
        r"\b(?:sn|s/n|serial(?:\s*number)?)(?:\s+is\s+|\s*[:=]\s*)([A-Za-z0-9-]{5,})\b",
        re.IGNORECASE,
    )

    # Prompt injection: overriding verbs must target instruction-like nouns, so a
    # legitimate "disregard my last message" is not blocked.
    INJECTION_PATTERNS = [
        re.compile(
            r"\b(?:ignore|disregard|forget|override|bypass|skip)\s+"
            r"(?:(?:all|any|your|the|these|those|previous|prior|above|earlier|original|initial|system|safety|current)\s+){0,3}"
            r"(?:instructions?|prompts?|rules?|guidelines?|directives?|policies|programming|training|constraints?)\b",
            re.IGNORECASE,
        ),
        re.compile(r"\byou\s+are\s+now\b", re.IGNORECASE),
        re.compile(r"\bsystem\s+prompt\b", re.IGNORECASE),
        re.compile(r"\bjailbreak\b", re.IGNORECASE),
        re.compile(r"\bpretend\s+(?:to\s+be|you\s+are)\b", re.IGNORECASE),
    ]

    @classmethod
    def _is_secret_candidate(cls, text: str, match: re.Match[str], require_digit: bool = False) -> bool:
        candidate = match.group(1)
        # Part of a contraction ("doesn't" -> captured "doesn" followed by "'").
        end = match.end(1)
        if end < len(text) and text[end] == "'":
            return False
        if candidate.lower() in cls._COMMON_CONTINUATIONS:
            return False
        if require_digit and not any(ch.isdigit() for ch in candidate):
            return False
        return True

    @classmethod
    def sanitize_and_inspect(cls, message: str) -> tuple[str, bool, str]:
        raw = message.strip()
        is_safe = True
        for pattern in cls.INJECTION_PATTERNS:
            if pattern.search(raw):
                logger.warning(f"Prompt injection attempt detected: {raw[:40]}")
                is_safe = False
                break

        redacted = raw
        has_pii = False

        if cls.API_KEY_PATTERN.search(redacted):
            redacted = cls.API_KEY_PATTERN.sub("[REDACTED_API_KEY]", redacted)
            has_pii = True

        def redact_password(match: re.Match[str]) -> str:
            if not cls._is_secret_candidate(match.string, match):
                return match.group(0)
            return "password: [REDACTED_SECRET]"

        after_password = cls.PASSWORD_PATTERN.sub(redact_password, redacted)
        if after_password != redacted:
            redacted = after_password
            has_pii = True

        def mask_serial(match: re.Match[str]) -> str:
            if not cls._is_secret_candidate(match.string, match, require_digit=True):
                return match.group(0)
            last4 = match.group(1)[-4:]
            return f"serial: [REDACTED_SERIAL_...{last4}]"

        after_serial = cls.SERIAL_PATTERN.sub(mask_serial, redacted)
        if after_serial != redacted:
            redacted = after_serial
            has_pii = True

        if has_pii:
            logger.info("Redacted sensitive credentials/serial numbers from user input.")

        isolated_message = f"<user_input>\n{redacted}\n</user_input>"
        return isolated_message, is_safe, redacted
