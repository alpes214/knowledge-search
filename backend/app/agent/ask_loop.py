# Pattern adapted from agent-platform/agent_platform/agent/loop.py.

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

_RETRIABLE_LLM_EXCEPTIONS = (
    httpx.ConnectError,
    httpx.TimeoutException,
    APIConnectionError,
    APITimeoutError,
    InternalServerError,
    RateLimitError,
)
_MAX_TOKENS_PER_REPLY = 1024


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
    input_tokens = 0
    output_tokens = 0
    iterations_done = 0

    try:
        for _ in range(max_iterations):
            iterations_done += 1
            if is_disconnected is not None and await is_disconnected():
                return

            resp = await _call_llm(llm_client, messages=messages, tools=tools)
            d_in, d_out = _token_deltas(resp)
            input_tokens += d_in
            output_tokens += d_out

            msg = resp.choices[0].message
            tool_calls = getattr(msg, 'tool_calls', None) or []

            if msg.content:
                final_text_parts.append(msg.content)
                yield text_event(msg.content)

            if not tool_calls:
                final_answer = '\n'.join(final_text_parts).strip()
                yield done_event(
                    answer=final_answer,
                    citations=_parse_citations(final_answer, chunks_seen),
                )
                return

            messages.append(_assistant_message(msg.content, tool_calls))

            for tc in tool_calls:
                try:
                    arguments = json.loads(tc.function.arguments)
                except (json.JSONDecodeError, TypeError):
                    yield _malformed_tool_call_event(tc.function.arguments)
                    return

                yield tool_use_event(id=tc.id, name=tc.function.name, arguments=arguments)

                try:
                    result_str, chunks = await dispatch(tc.function.name, arguments, session)
                except ToolFailed as e:
                    yield _tool_failed_event(e)
                    return

                chunks_seen.extend(chunks)
                yield tool_result_event(id=tc.id, result=result_str, chunks=chunks)
                messages.append(_tool_message(tc.id, result_str))

        yield _iteration_limit_event(max_iterations)
    except LLMUnavailable as e:
        yield _llm_unavailable_event(e)
    except Exception as e:
        log.exception('ask_loop crashed')
        yield _internal_error_event(e)
    finally:
        _log_completion(start, iterations_done, input_tokens, output_tokens)


async def _call_llm(
    client: LLMClient, *, messages: list[dict[str, Any]], tools: list[dict[str, Any]]
) -> Any:
    try:
        return await client.chat.completions.create(
            model=settings.llm_model,
            messages=messages,
            tools=tools,
            max_tokens=_MAX_TOKENS_PER_REPLY,
        )
    except _RETRIABLE_LLM_EXCEPTIONS as e:
        raise LLMUnavailable(str(e) or e.__class__.__name__) from e


def _token_deltas(resp: Any) -> tuple[int, int]:
    usage = getattr(resp, 'usage', None)
    return (
        getattr(usage, 'prompt_tokens', 0) or 0,
        getattr(usage, 'completion_tokens', 0) or 0,
    )


def _assistant_message(content: str | None, tool_calls: list[Any]) -> dict[str, Any]:
    return {
        'role': 'assistant',
        'content': content,
        'tool_calls': [
            {
                'id': tc.id,
                'type': 'function',
                'function': {'name': tc.function.name, 'arguments': tc.function.arguments},
            }
            for tc in tool_calls
        ],
    }


def _tool_message(tool_call_id: str, result: str) -> dict[str, Any]:
    return {'role': 'tool', 'tool_call_id': tool_call_id, 'content': result}


def _log_completion(
    start: float, iterations: int, input_tokens: int, output_tokens: int
) -> None:
    latency_ms = int((time.monotonic() - start) * 1000)
    log.info(
        'ask completed iterations=%d input_tokens=%d output_tokens=%d latency_ms=%d',
        iterations, input_tokens, output_tokens, latency_ms,
    )


def _malformed_tool_call_event(arguments_raw: str) -> AgentEvent:
    return error_event(
        code='malformed_tool_call',
        detail=f'invalid JSON in tool arguments: {arguments_raw!r}',
        retriable=False,
    )


def _tool_failed_event(e: ToolFailed) -> AgentEvent:
    return error_event(code=e.code, detail=e.detail, retriable=True)


def _iteration_limit_event(max_iterations: int) -> AgentEvent:
    return error_event(
        code='iteration_limit_exceeded',
        detail=f'agent did not produce a final answer in {max_iterations} iterations',
        retriable=False,
    )


def _llm_unavailable_event(e: LLMUnavailable) -> AgentEvent:
    return error_event(
        code='llm_unavailable',
        detail=f'LLM service unavailable: {e}',
        retriable=True,
    )


def _internal_error_event(e: Exception) -> AgentEvent:
    # Redact str(e) -- only the class name reaches the client.
    return error_event(
        code='internal',
        detail=f'internal error: {e.__class__.__name__}',
        retriable=False,
    )


_INLINE_MARKER = re.compile(r'\[(\d+)\]')
_SOURCE_LINE = re.compile(
    r'^\[(\d+)\]\s+(?P<filename>[^,]+),\s*page\s+(?P<page>\d+)(?:,\s*"(?P<heading>[^"]*)")?',
    re.MULTILINE,
)


def _parse_citations(answer: str, chunks_seen: list[dict[str, Any]]) -> list[Citation]:
    if not answer:
        return []
    cited = _cited_marker_numbers(answer)
    if not cited:
        return []
    sources = _source_lines(answer)
    citations: list[Citation] = []
    for n in cited:
        src = sources.get(n)
        if src is None:
            continue
        match = _find_chunk(chunks_seen, src['filename'], src['page'], src['heading'])
        citations.append(_make_citation(n, src, match))
    return citations


def _cited_marker_numbers(answer: str) -> list[int]:
    return sorted({int(m.group(1)) for m in _INLINE_MARKER.finditer(answer)})


def _source_lines(answer: str) -> dict[int, dict[str, Any]]:
    sources: dict[int, dict[str, Any]] = {}
    for m in _SOURCE_LINE.finditer(answer):
        n = int(m.group(1))
        sources[n] = {
            'filename': m.group('filename').strip(),
            'page': int(m.group('page')),
            'heading': (m.group('heading') or '').strip() or None,
        }
    return sources


def _make_citation(n: int, src: dict[str, Any], match: dict[str, Any] | None) -> Citation:
    return {
        'n': n,
        'chunk_id': int(match['chunk_id']) if match else 0,
        'document_id': str(match['document_id']) if match else '',
        'filename': src['filename'],
        'page': src['page'],
        'heading': src['heading'],
    }


def _normalize_heading(s: str | None) -> str:
    # The LLM may strip markdown bold (**Field 63.1**) when citing.
    return (s or '').replace('*', '').strip().lower()


def _find_chunk(
    chunks: list[dict[str, Any]], filename: str, page: int, heading: str | None
) -> dict[str, Any] | None:
    same_page = [c for c in chunks if c.get('filename') == filename and c.get('page') == page]
    if not same_page:
        return None
    target = _normalize_heading(heading)
    if not target:
        return same_page[0]
    for c in same_page:
        h = _normalize_heading(c.get('heading'))
        if target in h or h in target:
            return c
    return same_page[0]
