"""A LangChain chat model backed by the T2 gateway.

WHY THIS EXISTS AT ALL
----------------------
The vendored engine's nodes are LangChain runnables: they do
`ChatPromptTemplate | llm.bind_tools(tools)`. To reuse them we must hand them
something that quacks like a `BaseChatModel`.

The obvious alternative is the engine's own `tradingagents.llm_clients`, and it
is wrong for two independent reasons:

  1. **It bypasses the budget.** Every committee call would go straight to a
     provider SDK — no spend ledger, no daily ceiling, no reroute logging.
     T2's entire purpose is that all 14 agents route through one gateway, and
     using the engine's clients would silently defeat it. This is the real
     argument; the second one is only money.
  2. It needs `langchain-anthropic`, `langchain-openai`,
     `langchain-google-genai` and `langchain-aws` — 21 packages T6 measured
     and deliberately excluded.

So: one small adapter, ~1 abstract method of real work, and every agent call
keeps landing in the spend ledger.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.utils.function_calling import convert_to_openai_tool
from pydantic import ConfigDict, Field

from desk.llm import LLMGateway

_ROLES: dict[type[BaseMessage], str] = {
    SystemMessage: "system",
    HumanMessage: "user",
    AIMessage: "assistant",
}


def _role_of(message: BaseMessage) -> str:
    for cls, role in _ROLES.items():
        if isinstance(message, cls):
            return role
    if isinstance(message, ToolMessage):
        return "tool"
    # `type` is LangChain's own discriminator and is the honest fallback.
    return str(getattr(message, "type", "user"))


def to_payload(messages: Sequence[BaseMessage]) -> list[dict[str, Any]]:
    """LangChain messages -> the OpenAI-shaped dicts litellm expects."""
    out: list[dict[str, Any]] = []
    for message in messages:
        entry: dict[str, Any] = {
            "role": _role_of(message),
            "content": (
                message.content
                if isinstance(message.content, str)
                else str(message.content)
            ),
        }
        if isinstance(message, ToolMessage):
            entry["tool_call_id"] = message.tool_call_id
        calls = getattr(message, "tool_calls", None)
        if calls:
            entry["tool_calls"] = [
                {
                    "id": c.get("id", ""),
                    "type": "function",
                    "function": {
                        "name": c.get("name", ""),
                        "arguments": json.dumps(c.get("args", {})),
                    },
                }
                for c in calls
            ]
        out.append(entry)
    return out


def _tool_calls_from(response: Any) -> list[dict[str, Any]]:
    """Recover tool calls from the provider's raw response.

    Returns LangChain's tool-call shape. A malformed `arguments` string is
    surfaced as an empty dict rather than raising: a model that emits bad JSON
    should fail in the node that inspects the call, where the agent name is
    known, not deep inside the adapter.
    """
    try:
        raw = response.choices[0].message.tool_calls or []
    except (AttributeError, IndexError, TypeError):
        return []
    parsed: list[dict[str, Any]] = []
    for call in raw:
        try:
            args = json.loads(call.function.arguments or "{}")
        except (ValueError, AttributeError):
            args = {}
        parsed.append({
            "name": getattr(getattr(call, "function", None), "name", ""),
            "args": args if isinstance(args, dict) else {"value": args},
            "id": getattr(call, "id", "") or "",
            "type": "tool_call",
        })
    return parsed


class DeskChatModel(BaseChatModel):
    """Everything the engine's nodes need, routed through `desk/llm.py`."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    gateway: LLMGateway
    agent: str
    workflow: str = "W2"
    run_id: str = "unassigned"
    bound_tools: list[dict[str, Any]] = Field(default_factory=list)

    @property
    def _llm_type(self) -> str:
        return "desk-gateway"

    def bind_tools(self, tools: Sequence[Any], **kwargs: Any) -> DeskChatModel:
        """Return a copy carrying converted tool schemas.

        BaseChatModel's default raises NotImplementedError, and the engine's
        analysts all call this — so without it every analyst node dies on
        construction.
        """
        converted = [convert_to_openai_tool(t) for t in tools]
        return self.model_copy(update={"bound_tools": [*self.bound_tools, *converted]})

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        extra: dict[str, Any] = dict(kwargs)
        if self.bound_tools:
            extra["tools"] = self.bound_tools
        if stop:
            extra["stop"] = stop

        completion = self.gateway.complete(
            agent=self.agent,
            messages=to_payload(messages),
            workflow=self.workflow,
            run_id=self.run_id,
            **extra,
        )
        message = AIMessage(
            content=completion.content,
            tool_calls=_tool_calls_from(completion.raw),
            response_metadata={
                "model_requested": completion.call.model_requested,
                "model_served": completion.call.model_served,
                "cost_usd": completion.call.cost_usd,
                "rerouted": completion.call.rerouted,
            },
        )
        return ChatResult(generations=[ChatGeneration(message=message)])


def for_agent(
    gateway: LLMGateway, agent: str, workflow: str, run_id: str
) -> DeskChatModel:
    """The only way the graph should construct a model.

    Named rather than inlined so that a grep for `DeskChatModel(` finds every
    construction site, and so the tier lookup stays inside the gateway.
    """
    return DeskChatModel(gateway=gateway, agent=agent, workflow=workflow, run_id=run_id)


