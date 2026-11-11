"""Keeps the LLM's private reasoning out of the spoken reply.

Some models write their thinking into the answer, often fenced by lines of "=====".
Anything the agent says aloud passes through this filter first:
  - a leading block fenced by "=" lines is dropped
  - stray runs of "=" are removed
"""
from __future__ import annotations

import re

_RUN = re.compile(r"={3,}")
_MAX_HOLD = 4000


class ReasoningFilter:
    """Cleans one reply as it streams out of the model, piece by piece.

    Use: create one per reply, pass each piece of text through feed(), then call flush()."""

    def __init__(self) -> None:
        self._buf = ""
        self._mode = "start"

    def feed(self, text: str) -> str:
        """Take the next piece of the reply and return the part that is safe to speak.

        At the start of a reply, text is held back until we know whether it opens with a
        fenced reasoning block. Once the reply is under way, text passes straight through."""
        if self._mode == "start":
            self._buf += text
            s = self._buf.lstrip()
            if not s:
                return ""
            if s[0] != "=":
                self._mode = "pass"
                text, self._buf = self._buf, ""
            else:
                rest = self._after_fence(s)
                if rest is None:
                    if len(self._buf) > _MAX_HOLD:      # never-closed block: drop it
                        self._buf, self._mode = "", "pass"
                    return ""
                self._mode = "pass"
                text, self._buf = rest.lstrip("\n"), ""
        out = self._buf + text
        keep = len(out) - len(out.rstrip("="))            # a run may continue in the next chunk
        self._buf = out[len(out) - keep:] if keep else ""
        out = out[:len(out) - keep] if keep else out
        return _RUN.sub("", out)

    @staticmethod
    def _after_fence(s: str) -> str | None:
        """Text after a block that opens and closes with a line of "=". None while incomplete."""
        opened = len(s) - len(s.lstrip("="))
        if opened == len(s):
            return None                                  # opening line still arriving
        close = s.find("===", opened)
        if close == -1:
            return None
        end = close
        while end < len(s) and s[end] == "=":
            end += 1
        return None if end == len(s) else s[end:]         # closing line may still be arriving

    def flush(self) -> str:
        """Call once at the end of the reply. Returns anything still held back that is safe
        to speak (nothing, if the reply was only an unfinished reasoning block)."""
        if self._mode == "start":
            return ""
        out, self._buf = self._buf, ""
        return _RUN.sub("", out) if len(out) < 3 else ""
