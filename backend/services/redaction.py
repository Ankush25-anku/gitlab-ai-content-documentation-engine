"""Removes secrets from uploaded inputs before they are stored or sent to any model."""
import re

PATTERNS: list[tuple[str, re.Pattern]] = [
    ("gitlab_token", re.compile(r"\bgl(?:pat|dt|rt|ptt|ft|imt|agent|oas|cbt|soat|ffct)-[A-Za-z0-9_\-]{20,}\b")),
    ("github_token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b")),
    ("aws_access_key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("google_api_key", re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b")),
    ("openai_key", re.compile(r"\bsk-[A-Za-z0-9_\-]{20,}\b")),
    ("slack_token", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}\b")),
    ("private_key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.S)),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\b")),
    ("password_assignment", re.compile(r"(?i)\b(password|passwd|secret|api_key|apikey|token)\s*[:=]\s*['\"]?[^\s'\"]{8,}")),
    ("email", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")),
]
SAFE_EMAIL_DOMAINS = ("example.com", "example.org", "gitlab.com")


def redact(text: str) -> tuple[str, list[dict]]:
    """Return the redacted text and a list of {type, count} findings (never the values)."""
    findings: dict[str, int] = {}

    for name, rx in PATTERNS:
        def repl(m: re.Match, name=name) -> str:
            value = m.group(0)
            if name == "email" and value.lower().endswith(SAFE_EMAIL_DOMAINS):
                return value
            findings[name] = findings.get(name, 0) + 1
            if name == "password_assignment":
                return f"{m.group(1)}=[REDACTED]"
            return f"[REDACTED:{name}]"
        text = rx.sub(repl, text)
    return text, [{"type": k, "count": v} for k, v in findings.items()]
