from client.llm_client import LLMClient
import asyncio


async def main():
    client = LLMClient()
    messages = [{
        "role": "user",
        "content": "你好"
    }]
    async for event in client.chat_completion(messages, True):
        print(event)

    print("dddddddddddddd")


asyncio.run(main())
