import asyncio

from spike_ai_provider_adapters.adapters.anthropic_sdk import create_sdk_provider
from spike_ai_provider_adapters.config import (
  build_real_context,
  build_real_model,
  resolve_api_key,
)


async def main():
  model = build_real_model()
  context = build_real_context()
  provider = create_sdk_provider()
  opts = type("Opts", (), {"api_key": resolve_api_key(), "max_tokens": 128, "signal": None})()
  s = provider.stream(model, context, opts)
  async for ev in s:
      print("EVENT", ev.type, ev.text, ev.reason, ev.message)
  msg = await s.result()
  print("FINAL", msg.stop_reason, [c.text for c in msg.content], msg.error_message)

asyncio.run(main())
