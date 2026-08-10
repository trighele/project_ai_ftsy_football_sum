"""The Claude edge: one summary, streamed as Claude writes it.

Streaming is not decoration. A long episode's summary takes minutes to write,
and asking for it in one non-streaming call leaves an HTTP connection idle
long enough to be dropped; the SDK's streaming helper also hands the text back
a delta at a time, which is exactly what the browser is shown.

This module is imported only when the edge is actually built, so nothing
outside a real run pays for the SDK.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import anthropic

from project_ai_ftsy_football_sum.services.summarize import SummaryRequest

#: Room for a long episode's summary and the thinking that precedes it.
MAX_TOKENS = 16000

#: Claude decides for itself how much thinking a transcript warrants.
THINKING: dict[str, Any] = {"type": "adaptive"}

#: Summarizing is reading work rather than reasoning work, so it does not need
#: the depth — or the tokens — that a higher effort would spend on it.
OUTPUT_CONFIG: dict[str, Any] = {"effort": "medium"}


class ClaudeClient:
    """Talks to the Claude API. Building one needs credentials.

    The SDK itself does not check for them until a request is made, which
    would mean a missing API key first appearing halfway through somebody's
    run. The readiness pill builds every edge precisely to find out whether a
    run could happen, so the check is brought forward to here.
    """

    def __init__(self, client: anthropic.Anthropic | None = None) -> None:
        if client is not None:
            self.client = client
            return
        self.client = anthropic.Anthropic()
        if not (self.client.api_key or self.client.auth_token):
            raise anthropic.AnthropicError(
                "No Claude credentials: set ANTHROPIC_API_KEY in the environment."
            )

    def stream(self, request: SummaryRequest) -> Iterator[str]:
        """Yield the summary's text in the order Claude writes it."""
        with self.client.messages.stream(
            model=request.model,
            max_tokens=MAX_TOKENS,
            thinking=THINKING,
            output_config=OUTPUT_CONFIG,
            system=list(request.system),
            messages=[{"role": "user", "content": request.user}],
        ) as stream:
            yield from stream.text_stream
