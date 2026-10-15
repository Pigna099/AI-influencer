"""Outbound content policy scan: keep minors and ambiguous-age content out of replies.

Two tiers:
- hard terms block immediately (underage references are never acceptable);
- soft terms (child/kid/minor/teen/young) block only when the same reply is sexual.
"""

import re

HARD_PATTERNS = (
    r"\b(?:underage|under[- ]?aged|loli|shota|pre[- ]?teen|jailbait|schoolgirl|schoolboy)\b",
    r"\b(?:under|below)\s+18\b",
    r"\b(?:1[0-7]|[0-9])\s*(?:yo|y\.o\.|years?[ -]old)\b",
    r"\b(?:barely|just)\s+(?:turned\s+)?(?:18|eighteen)\b",
)

SOFT_PATTERN = re.compile(r"\b(?:child|children|kid|kids|minor|minors|teen|teens|teenage|teenager|young girl|young boy|school)\b")
SEXUAL_PATTERN = re.compile(
    r"\b(?:sexy|sexual|naked|nude|nsfw|fuck|horny|erotic|lingerie|undress|in bed|bedroom|kiss|"
    r"body|tits|ass|pussy|dick|cock|orgasm)\b",
    re.IGNORECASE,
)

HARD = tuple(re.compile(pattern, re.IGNORECASE) for pattern in HARD_PATTERNS)


def scan_policy(text: str) -> list[str]:
    """Return the list of policy issues found in the text (empty when clean)."""
    if not text:
        return []
    issues: list[str] = []
    for pattern in HARD:
        if pattern.search(text):
            issues.append(f"hard:{pattern.pattern[:40]}")
    if SOFT_PATTERN.search(text) and SEXUAL_PATTERN.search(text):
        issues.append("soft_age_plus_sexual")
    return issues
