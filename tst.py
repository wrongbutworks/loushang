import asyncio
from examples.ai.kimi_openai_stream import _resolve_api_key, _build_context, _build_options, PROVIDER_ID, ENDPOINT_ID, MODEL_ID
from loushang.ai import get_model


async def main():
  api_key = _resolve_api_key()
  model = get_model(PROVIDER_ID, ENDPOINT_ID, MODEL_ID)
  events = await model.stream(_build_context(), _build_options(api_key))
  async for event in events:
      print(event)
  final = await events.result()
  print("error_message =", repr(final.error_message))


asyncio.run(main())

