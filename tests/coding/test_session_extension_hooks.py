from __future__ import annotations

import asyncio

from loushang.agent import Agent
from loushang.ai.types import TextPart, UserMessage
from loushang.coding.extensions import ContextResult, ExtensionRunner, LoadedExtension
from loushang.coding.session.extension_hooks import ExtensionHooks


def _user_message(text: str) -> UserMessage:
    return UserMessage(role="user", content=[TextPart(type="text", text=text)], timestamp=0.0)


def test_extension_hooks_compose_existing_transform_with_extension_context(tmp_path) -> None:
    seen: list[str] = []

    async def _existing_transform(messages, signal):
        del signal
        return messages + [_user_message("from-existing")]

    def _extension_context(event, ctx):
        seen.append(f"{event.messages[-1].content[0].text}:{ctx.cwd}")
        return ContextResult(messages=event.messages + [_user_message("from-extension")])

    agent = Agent(transform_context=_existing_transform)
    ExtensionHooks(
        agent=agent,
        extension_runner=ExtensionRunner(
            [
                LoadedExtension(
                    name="context",
                    source_path=tmp_path / "context.py",
                    hooks={"context": [_extension_context]},
                )
            ]
        ),
        get_cwd=lambda: "/tmp/project",
    ).install()

    transformed = asyncio.run(agent.transform_context([_user_message("base")], None))

    assert [message.content[0].text for message in transformed] == [
        "base",
        "from-existing",
        "from-extension",
    ]
    assert seen == ["from-existing:/tmp/project"]
