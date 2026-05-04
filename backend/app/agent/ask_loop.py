# Pattern adapted from agent-platform/agent_platform/agent/loop.py
# Stripped: ticket persistence (Message/Ticket DB writes), Kafka publishing,
# history loading. Added: error event emission for SSE, client-disconnect
# detection, malformed tool_calls handling, citation parsing for done event,
# server-side argument validation in dispatch (lives in tools.py).

import json
import logging
import re
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any, Protocol

import httpx
from openai import APIConnectionError, APITimeoutError, InternalServerError, RateLimitError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.agent.events import (
    AgentEvent,
    Citation,
    done_event,
    error_event,
    text_event,
    tool_result_event,
    tool_use_event,
)
from backend.app.agent.tools import LLMUnavailable, ToolFailed
from backend.app.config import settings

log = logging.getLogger(__name__)


class LLMClient(Protocol):
    class _Chat(Protocol):
        class _Completions(Protocol):
            async def create(self, **kwargs: Any) -> Any: ...

        completions: '_Completions'

    chat: '_Chat'


_DispatchFn = Callable[
    [str, dict[str, Any], AsyncSession],
    Awaitable[tuple[str, list[dict[str, Any]]]],
]


async def run(
    *,
    question: str,
    tools: list[dict[str, Any]],
    dispatch: _DispatchFn,
    system_prompt: str,
    llm_client: LLMClient,
    session: AsyncSession,
    max_iterations: int,
    is_disconnected: Callable[[], Awaitable[bool]] | None = None,
) -> AsyncIterator[AgentEvent]:
    start = time.monotonic()
    messages: list[dict[str, Any]] = [
        {'role': 'system', 'content': system_prompt},
        {'role': 'user', 'content': question},
    ]
    final_text_parts: list[str] = []
    chunks_seen: list[dict[str, Any]] = []
    input_tokens_total = 0
    output_tokens_total = 0
    iterations_done = 0

    try:
        for iteration in range(max_iterations):
            iterations_done = iteration + 1
            if is_disconnected is not None and await is_disconnected():
                return

            try:
                resp = await llm_client.chat.completions.create(
                    model=settings.llm_model,
                    messages=messages,
                    tools=tools,
                    max_tokens=1024,
                )
            except (
                httpx.ConnectError,
                httpx.TimeoutException,
                APIConnectionError,
                APITimeoutError,
                InternalServerError,
                RateLimitError,
            ) as e:
                raise LLMUnavailable(str(e) or e.__class__.__name__) from e

            usage = getattr(resp, 'usage', None)
            if usage is not None:
                input_tokens_total += getattr(usage, 'prompt_tokens', 0) or 0
                output_tokens_total += getattr(usage, 'completion_tokens', 0) or 0

            msg = resp.choices[0].message
            tool_calls = getattr(msg, 'tool_calls', None) or []

            if msg.content:
                final_text_parts.append(msg.content)
                yield text_event(msg.content)

            if not tool_calls:
                final = '\n'.join(final_text_parts).strip()
                citations = _parse_citations(final, chunks_seen)
                yield done_event(answer=final, citations=citations)
                return

            messages.append(_assistant_message(msg))

            for tc in tool_calls:
                arguments_raw = tc.function.arguments
                try:
                    arguments = json.loads(arguments_raw)
                except (json.JSONDecodeError, TypeError):
                    yield error_event(
                        code='malformed_tool_call',
                        detail=f'invalid JSON in tool arguments: {arguments_raw!r}',
                        retriable=False,
                    )
                    return

                yield tool_use_event(
                    id=tc.id, name=tc.function.name, arguments=arguments
                )

                try:
                    result_str, chunks = await dispatch(
                        tc.function.name, arguments, session
                    )
                except ToolFailed as e:
                    yield error_event(code=e.code, detail=e.detail, retriable=True)
                    return

                chunks_seen.extend(chunks)
                yield tool_result_event(id=tc.id, result=result_str, chunks=chunks)
                messages.append(
                    {
                        'role': 'tool',
                        'tool_call_id': tc.id,
                        'content': result_str,
                    }
                )

        yield error_event(
            code='iteration_limit_exceeded',
            detail=f'agent did not produce a final answer in {max_iterations} iterations',
            retriable=False,
        )
    except LLMUnavailable as e:
        yield error_event(
            code='llm_unavailable', detail=f'LLM service unavailable: {e}', retriable=True
        )
    except Exception as e:
        log.exception('ask_loop crashed')
        yield error_event(
            code='internal', detail=f'internal error: {e.__class__.__name__}', retriable=False
        )
    finally:
        latency_ms = int((time.monotonic() - start) * 1000)
        log.info(
            'ask completed iterations=%d input_tokens=%d output_tokens=%d latency_ms=%d',
            iterations_done, input_tokens_total, output_tokens_total, latency_ms,
        )


def _assistant_message(sdk_message: Any) -> dict[str, Any]:
    tool_calls = getattr(sdk_message, 'tool_calls', None) or []
    return {
        'role': 'assistant',
        'content': sdk_message.content,
        'tool_calls': [
            {
                'id': tc.id,
                'type': 'function',
                'function': {
                    'name': tc.function.name,
                    'arguments': tc.function.arguments,
                },
            }
            for tc in tool_calls
        ],
    }


_INLINE_MARKER = re.compile(r'\[(\d+)\]')
_SOURCE_LINE = re.compile(
    r'^\[(\d+)\]\s+(?P<filename>[^,]+),\s*page\s+(?P<page>\d+)(?:,\s*"(?P<heading>[^"]*)")?',
    re.MULTILINE,
)


def _parse_citations(answer: str, chunks_seen: list[dict[str, Any]]) -> list[Citation]:
    if not answer:
        return []
    cited_numbers = sorted({int(m.group(1)) for m in _INLINE_MARKER.finditer(answer)})
    if not cited_numbers:
        return []
    sources: dict[int, dict[str, Any]] = {}
    for m in _SOURCE_LINE.finditer(answer):
        n = int(m.group(1))
        sources[n] = {
            'filename': m.group('filename').strip(),
            'page': int(m.group('page')),
            'heading': (m.group('heading') or '').strip() or None,
        }
    citations: list[Citation] = []
    for n in cited_numbers:
        src = sources.get(n)
        if src is None:
            continue
        match = _find_chunk(chunks_seen, src['filename'], src['page'], src['heading'])
        citations.append(
            {
                'n': n,
                'chunk_id': int(match['chunk_id']) if match else 0,
                'document_id': str(match['document_id']) if match else '',
                'filename': src['filename'],
                'page': src['page'],
                'heading': src['heading'],
            }
        )
    return citations


def _find_chunk(
    chunks: list[dict[str, Any]], filename: str, page: int, heading: str | None
) -> dict[str, Any] | None:
    # Heading text may include markdown bold (`**Field 63.1**`) the LLM stripped
    # in its citation -- compare loosely on substring after stripping markdown
    # asterisks and trimming whitespace.
    target = (heading or '').replace('*', '').strip().lower()
    for c in chunks:
        if c.get('filename') != filename or c.get('page') != page:
            continue
        chunk_heading = (c.get('heading') or '').replace('*', '').strip().lower()
        if not target or target in chunk_heading or chunk_heading in target:
            return c
    # Fallback: filename+page only (heading mismatch).
    for c in chunks:
        if c.get('filename') == filename and c.get('page') == page:
            return c
    return None
