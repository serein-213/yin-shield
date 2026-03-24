"""OpenAI-compatible wrapper for automatic masking and unmasking."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, AsyncIterator, Dict, Iterable, Iterator, List, Optional, Tuple

from .core import Shield, ShieldSession


class ShieldedOpenAI:
    """Wrap an OpenAI client and transparently protect message content."""

    def __init__(
        self,
        client: Optional[Any] = None,
        shield: Optional[Shield] = None,
        **client_kwargs: Any,
    ) -> None:
        self._shield = shield or Shield()
        self._client = client or self._build_default_client(**client_kwargs)
        self.chat = _ChatProxy(self._client.chat, self._shield)
        if hasattr(self._client, "responses"):
            self.responses = _ResponsesProxy(self._client.responses, self._shield)

    @property
    def raw_client(self) -> Any:
        return self._client

    @staticmethod
    def _build_default_client(**client_kwargs: Any) -> Any:
        try:
            from openai import OpenAI  # type: ignore
        except ImportError as exc:
            raise ImportError(
                "openai is not installed. Install it with `pip install openai` "
                "or pass an existing client to ShieldedOpenAI(client=...)."
            ) from exc
        return OpenAI(**client_kwargs)


class ShieldedAsyncOpenAI:
    """Async variant of ShieldedOpenAI."""

    def __init__(
        self,
        client: Optional[Any] = None,
        shield: Optional[Shield] = None,
        **client_kwargs: Any,
    ) -> None:
        self._shield = shield or Shield()
        self._client = client or self._build_default_client(**client_kwargs)
        self.chat = _AsyncChatProxy(self._client.chat, self._shield)
        if hasattr(self._client, "responses"):
            self.responses = _AsyncResponsesProxy(self._client.responses, self._shield)

    @property
    def raw_client(self) -> Any:
        return self._client

    @staticmethod
    def _build_default_client(**client_kwargs: Any) -> Any:
        try:
            from openai import AsyncOpenAI  # type: ignore
        except ImportError as exc:
            raise ImportError(
                "openai is not installed. Install it with `pip install openai` "
                "or pass an existing client to ShieldedAsyncOpenAI(client=...)."
            ) from exc
        return AsyncOpenAI(**client_kwargs)


class _ChatProxy:
    def __init__(self, chat_resource: Any, shield: Shield) -> None:
        self.completions = _ChatCompletionsProxy(chat_resource.completions, shield)


class _AsyncChatProxy:
    def __init__(self, chat_resource: Any, shield: Shield) -> None:
        self.completions = _AsyncChatCompletionsProxy(chat_resource.completions, shield)


class _ChatCompletionsProxy:
    def __init__(self, completions_resource: Any, shield: Shield) -> None:
        self._completions = completions_resource
        self._shield = shield

    def create(self, *args: Any, **kwargs: Any) -> Any:
        messages = kwargs.get("messages")
        if messages is None and len(args) >= 2:
            messages = args[1]

        if messages is None:
            return self._completions.create(*args, **kwargs)

        masked_messages, mapping = mask_messages(messages, self._shield, session=self._shield.session)

        if "messages" in kwargs:
            kwargs = dict(kwargs)
            kwargs["messages"] = masked_messages
            response = self._completions.create(*args, **kwargs)
        else:
            args_list = list(args)
            args_list[1] = masked_messages
            response = self._completions.create(*args_list, **kwargs)

        if kwargs.get("stream") is True:
            return _StreamWrapper(response, mapping, self._shield)

        return unmask_response(response, mapping, self._shield)


class _AsyncChatCompletionsProxy:
    def __init__(self, completions_resource: Any, shield: Shield) -> None:
        self._completions = completions_resource
        self._shield = shield

    async def create(self, *args: Any, **kwargs: Any) -> Any:
        messages = kwargs.get("messages")
        if messages is None and len(args) >= 2:
            messages = args[1]

        if messages is None:
            return await self._completions.create(*args, **kwargs)

        masked_messages, mapping = mask_messages(messages, self._shield, session=self._shield.session)
        call_kwargs, call_args = _replace_payload("messages", masked_messages, args, kwargs, arg_index=1)
        response = await self._completions.create(*call_args, **call_kwargs)

        if call_kwargs.get("stream") is True:
            return _AsyncStreamWrapper(response, mapping, self._shield)

        return unmask_response(response, mapping, self._shield)


class _ResponsesProxy:
    def __init__(self, responses_resource: Any, shield: Shield) -> None:
        self._responses = responses_resource
        self._shield = shield

    def create(self, *args: Any, **kwargs: Any) -> Any:
        user_input = kwargs.get("input")
        if user_input is None and args:
            user_input = args[0]

        if user_input is None:
            return self._responses.create(*args, **kwargs)

        masked_input, mapping = mask_response_input(user_input, self._shield, session=self._shield.session)

        if "input" in kwargs:
            kwargs = dict(kwargs)
            kwargs["input"] = masked_input
            response = self._responses.create(*args, **kwargs)
        else:
            args_list = list(args)
            args_list[0] = masked_input
            response = self._responses.create(*args_list, **kwargs)

        if kwargs.get("stream") is True:
            return _StreamWrapper(response, mapping, self._shield)

        return unmask_response(response, mapping, self._shield)


class _AsyncResponsesProxy:
    def __init__(self, responses_resource: Any, shield: Shield) -> None:
        self._responses = responses_resource
        self._shield = shield

    async def create(self, *args: Any, **kwargs: Any) -> Any:
        user_input = kwargs.get("input")
        if user_input is None and args:
            user_input = args[0]

        if user_input is None:
            return await self._responses.create(*args, **kwargs)

        masked_input, mapping = mask_response_input(user_input, self._shield, session=self._shield.session)
        call_kwargs, call_args = _replace_payload("input", masked_input, args, kwargs, arg_index=0)
        response = await self._responses.create(*call_args, **call_kwargs)

        if call_kwargs.get("stream") is True:
            return _AsyncStreamWrapper(response, mapping, self._shield)

        return unmask_response(response, mapping, self._shield)


class _StreamWrapper:
    def __init__(self, stream: Iterable[Any], mapping: Dict[str, str], shield: Shield) -> None:
        self._stream = stream
        self._mapping = mapping
        self._shield = shield

    def __iter__(self) -> Iterator[Any]:
        for event in self._stream:
            yield unmask_response(event, self._mapping, self._shield)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._stream, name)

    def close(self) -> Any:
        close = getattr(self._stream, "close", None)
        if callable(close):
            return close()
        return None


class _AsyncStreamWrapper:
    def __init__(self, stream: Any, mapping: Dict[str, str], shield: Shield) -> None:
        self._stream = stream
        self._mapping = mapping
        self._shield = shield

    def __aiter__(self) -> AsyncIterator[Any]:
        return self

    async def __anext__(self) -> Any:
        try:
            event = await self._stream.__anext__()
        except StopAsyncIteration:
            raise
        return unmask_response(event, self._mapping, self._shield)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._stream, name)

    async def close(self) -> Any:
        close = getattr(self._stream, "close", None)
        if callable(close):
            result = close()
            if hasattr(result, "__await__"):
                return await result
            return result
        return None


def mask_messages(
    messages: Iterable[Any],
    shield: Shield,
    session: Optional[ShieldSession] = None,
) -> Tuple[List[Any], Dict[str, str]]:
    mapping: Dict[str, str] = {}
    masked_messages: List[Any] = []

    for message in messages:
        masked_messages.append(_mask_message(message, shield, mapping, session))

    if session is not None:
        return masked_messages, dict(session.replacements_to_originals)
    return masked_messages, mapping


def mask_response_input(
    user_input: Any,
    shield: Shield,
    session: Optional[ShieldSession] = None,
) -> Tuple[Any, Dict[str, str]]:
    mapping: Dict[str, str] = {}
    masked_input = _mask_response_input_item(user_input, shield, mapping, session)
    if session is not None:
        return masked_input, dict(session.replacements_to_originals)
    return masked_input, mapping


def _replace_payload(
    key: str,
    value: Any,
    args: Tuple[Any, ...],
    kwargs: Dict[str, Any],
    arg_index: int,
) -> Tuple[Dict[str, Any], Tuple[Any, ...]]:
    if key in kwargs:
        updated_kwargs = dict(kwargs)
        updated_kwargs[key] = value
        return updated_kwargs, args

    args_list = list(args)
    args_list[arg_index] = value
    return kwargs, tuple(args_list)


def _mask_message(
    message: Any,
    shield: Shield,
    mapping: Dict[str, str],
    session: Optional[ShieldSession],
) -> Any:
    cloned = deepcopy(message)

    if isinstance(cloned, dict):
        cloned["content"] = _mask_content(cloned.get("content"), shield, mapping, session)
        return cloned

    if hasattr(cloned, "content"):
        cloned.content = _mask_content(getattr(cloned, "content"), shield, mapping, session)
        return cloned

    return cloned


def _mask_content(
    content: Any,
    shield: Shield,
    mapping: Dict[str, str],
    session: Optional[ShieldSession],
) -> Any:
    if isinstance(content, str):
        masked, updated_mapping = shield.mask(content, mapping=None if session else mapping, session=session)
        mapping.clear()
        mapping.update(updated_mapping)
        return masked

    if isinstance(content, list):
        masked_parts: List[Any] = []
        for part in content:
            masked_parts.append(_mask_content_part(part, shield, mapping, session))
        return masked_parts

    return content


def _mask_content_part(
    part: Any,
    shield: Shield,
    mapping: Dict[str, str],
    session: Optional[ShieldSession],
) -> Any:
    cloned = deepcopy(part)

    if isinstance(cloned, dict):
        if cloned.get("type") == "text" and isinstance(cloned.get("text"), str):
            masked, updated_mapping = shield.mask(cloned["text"], mapping=None if session else mapping, session=session)
            mapping.clear()
            mapping.update(updated_mapping)
            cloned["text"] = masked
        return cloned

    if hasattr(cloned, "type") and getattr(cloned, "type") == "text" and hasattr(cloned, "text"):
        masked, updated_mapping = shield.mask(
            getattr(cloned, "text"),
            mapping=None if session else mapping,
            session=session,
        )
        mapping.clear()
        mapping.update(updated_mapping)
        cloned.text = masked
        return cloned

    return cloned


def _mask_response_input_item(
    item: Any,
    shield: Shield,
    mapping: Dict[str, str],
    session: Optional[ShieldSession],
) -> Any:
    if isinstance(item, str):
        masked, updated_mapping = shield.mask(item, mapping=None if session else mapping, session=session)
        mapping.clear()
        mapping.update(updated_mapping)
        return masked

    if isinstance(item, list):
        return [_mask_response_input_item(entry, shield, mapping, session) for entry in item]

    cloned = deepcopy(item)
    if isinstance(cloned, dict):
        if "content" in cloned:
            cloned["content"] = _mask_response_content(cloned["content"], shield, mapping, session)
        return cloned

    if hasattr(cloned, "content"):
        cloned.content = _mask_response_content(getattr(cloned, "content"), shield, mapping, session)
        return cloned

    return cloned


def _mask_response_content(
    content: Any,
    shield: Shield,
    mapping: Dict[str, str],
    session: Optional[ShieldSession],
) -> Any:
    if isinstance(content, str):
        masked, updated_mapping = shield.mask(content, mapping=None if session else mapping, session=session)
        mapping.clear()
        mapping.update(updated_mapping)
        return masked

    if isinstance(content, list):
        return [_mask_response_content_part(part, shield, mapping, session) for part in content]

    return content


def _mask_response_content_part(
    part: Any,
    shield: Shield,
    mapping: Dict[str, str],
    session: Optional[ShieldSession],
) -> Any:
    cloned = deepcopy(part)

    if isinstance(cloned, dict):
        part_type = cloned.get("type")
        if part_type in {"input_text", "text"} and isinstance(cloned.get("text"), str):
            masked, updated_mapping = shield.mask(cloned["text"], mapping=None if session else mapping, session=session)
            mapping.clear()
            mapping.update(updated_mapping)
            cloned["text"] = masked
        return cloned

    if hasattr(cloned, "type") and hasattr(cloned, "text"):
        if getattr(cloned, "type") in {"input_text", "text"}:
            masked, updated_mapping = shield.mask(
                getattr(cloned, "text"),
                mapping=None if session else mapping,
                session=session,
            )
            mapping.clear()
            mapping.update(updated_mapping)
            cloned.text = masked
        return cloned

    return cloned


def unmask_response(response: Any, mapping: Dict[str, str], shield: Shield) -> Any:
    if not mapping:
        return response

    if isinstance(response, dict):
        return _unmask_response_dict(response, mapping, shield)

    if hasattr(response, "choices"):
        _unmask_choices(getattr(response, "choices"), mapping, shield)
        return response

    if hasattr(response, "output"):
        _unmask_output(getattr(response, "output"), mapping, shield)
        if hasattr(response, "output_text") and isinstance(getattr(response, "output_text"), str):
            response.output_text = shield.unmask(getattr(response, "output_text"), mapping)
        return response

    return response


def _unmask_response_dict(response: Dict[str, Any], mapping: Dict[str, str], shield: Shield) -> Dict[str, Any]:
    cloned = deepcopy(response)
    choices = cloned.get("choices")
    if isinstance(choices, list):
        for choice in choices:
            if not isinstance(choice, dict):
                continue
            message = choice.get("message")
            if isinstance(message, dict):
                message["content"] = _unmask_content(message.get("content"), mapping, shield)
    output = cloned.get("output")
    if isinstance(output, list):
        _unmask_output(output, mapping, shield)
    if isinstance(cloned.get("output_text"), str):
        cloned["output_text"] = shield.unmask(cloned["output_text"], mapping)
    return cloned


def _unmask_choices(choices: Any, mapping: Dict[str, str], shield: Shield) -> None:
    for choice in choices:
        if isinstance(choice, dict):
            message = choice.get("message")
            if isinstance(message, dict):
                message["content"] = _unmask_content(message.get("content"), mapping, shield)
            elif hasattr(message, "content"):
                message.content = _unmask_content(getattr(message, "content"), mapping, shield)
            continue

        message = getattr(choice, "message", None)
        if hasattr(message, "content"):
            message.content = _unmask_content(getattr(message, "content"), mapping, shield)


def _unmask_output(output: Any, mapping: Dict[str, str], shield: Shield) -> None:
    for item in output:
        if isinstance(item, dict):
            content = item.get("content")
            if isinstance(content, list):
                item["content"] = [_unmask_output_part(part, mapping, shield) for part in content]
            continue

        content = getattr(item, "content", None)
        if isinstance(content, list):
            item.content = [_unmask_output_part(part, mapping, shield) for part in content]


def _unmask_content(content: Any, mapping: Dict[str, str], shield: Shield) -> Any:
    if isinstance(content, str):
        return shield.unmask(content, mapping)

    if isinstance(content, list):
        restored_parts: List[Any] = []
        for part in content:
            restored_parts.append(_unmask_content_part(part, mapping, shield))
        return restored_parts

    return content


def _unmask_content_part(part: Any, mapping: Dict[str, str], shield: Shield) -> Any:
    cloned = deepcopy(part)

    if isinstance(cloned, dict):
        if cloned.get("type") == "text" and isinstance(cloned.get("text"), str):
            cloned["text"] = shield.unmask(cloned["text"], mapping)
        return cloned

    if hasattr(cloned, "type") and getattr(cloned, "type") == "text" and hasattr(cloned, "text"):
        cloned.text = shield.unmask(getattr(cloned, "text"), mapping)
        return cloned

    return cloned


def _unmask_output_part(part: Any, mapping: Dict[str, str], shield: Shield) -> Any:
    cloned = deepcopy(part)

    if isinstance(cloned, dict):
        if cloned.get("type") == "output_text" and isinstance(cloned.get("text"), str):
            cloned["text"] = shield.unmask(cloned["text"], mapping)
        return cloned

    if hasattr(cloned, "type") and getattr(cloned, "type") == "output_text" and hasattr(cloned, "text"):
        cloned.text = shield.unmask(getattr(cloned, "text"), mapping)
        return cloned

    return cloned
