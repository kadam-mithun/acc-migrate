"""Untrusted source text (SPEC §10, §14 row 26).

Unity Catalog comments, tags, `constraints` and `generated_expression` are
written by whoever controls the source estate, so they are attacker-influencable
and reach three places that matter: Glue table parameters (SPEC §7), the
conversion record, and — via any agent-visible field — a model context.

:func:`sanitize_source_text` is applied at the model boundary, so a
`TableProfile` carrying raw source text cannot be constructed. It:

* strips control characters and zero-width code points (the characters that
  smuggle instructions past a human reviewer);
* normalises to NFC (so visually identical strings compare equal);
* caps at :data:`MAX_SOURCE_TEXT` characters and marks the truncation.

:func:`mark_untrusted` adds the `<x-untrusted src="uc:{field}">…</x-untrusted>`
marker, and is applied where the text can reach a model context. It is separate
because the marker is presentation: storing it in Glue parameters would corrupt
the value a client reads back.

`strategy.py` never interpolates source text into a rationale string — those are
template + enum only, and the text travels in `source_metadata` instead.
"""

from __future__ import annotations

import unicodedata

MAX_SOURCE_TEXT = 1024
TRUNCATION_MARKER = "…[truncated]"
UNTRUSTED_OPEN = '<x-untrusted src="uc:{field}">'
UNTRUSTED_CLOSE = "</x-untrusted>"

# Zero-width and bidirectional-override code points. Unicode category Cf covers
# most, but these are called out because they are the ones used to hide text.
_ZERO_WIDTH = frozenset(
    chr(code)
    for code in (
        0x200B,  # zero-width space
        0x200C,  # zero-width non-joiner
        0x200D,  # zero-width joiner
        0x200E,  # left-to-right mark
        0x200F,  # right-to-left mark
        0x2028,  # line separator
        0x2029,  # paragraph separator
        0x202A,  # left-to-right embedding
        0x202B,  # right-to-left embedding
        0x202C,  # pop directional formatting
        0x202D,  # left-to-right override
        0x202E,  # right-to-left override
        0x2060,  # word joiner
        0xFEFF,  # zero-width no-break space / BOM
    )
)


def _is_removable(char: str) -> bool:
    """True for control, format and zero-width characters.

    Tab, newline and carriage return are control characters too, and are removed:
    a newline in a Glue parameter or a log line is how one value becomes two.
    """
    return char in _ZERO_WIDTH or unicodedata.category(char) in {"Cc", "Cf"}


def sanitize_source_text(value: str) -> str:
    """Make one piece of UC-authored text safe to store, log and display.

    Idempotent: sanitising an already-sanitised string returns it unchanged,
    which matters because the model-boundary validator may run more than once.
    """
    if not isinstance(value, str):  # pragma: no cover - pydantic checks the type
        return value
    stripped = "".join(char for char in value if not _is_removable(char))
    normalised = unicodedata.normalize("NFC", stripped)
    if len(normalised) <= MAX_SOURCE_TEXT:
        return normalised
    keep = MAX_SOURCE_TEXT - len(TRUNCATION_MARKER)
    return normalised[:keep] + TRUNCATION_MARKER


def mark_untrusted(value: str, *, field: str) -> str:
    """Wrap sanitised text in the `<x-untrusted>` marker for a model context.

    Args:
        value: text that has already been through :func:`sanitize_source_text`.
        field: the UC field it came from, e.g. `"comment"` or `"tag:owner"`.
    """
    safe_field = sanitize_source_text(field).replace('"', "")
    return (
        f"{UNTRUSTED_OPEN.format(field=safe_field)}{sanitize_source_text(value)}{UNTRUSTED_CLOSE}"
    )


def was_truncated(value: str) -> bool:
    """True when :func:`sanitize_source_text` had to cut this value short."""
    return value.endswith(TRUNCATION_MARKER)
