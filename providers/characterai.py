import ujson
from typing import AsyncGenerator, List, Dict, Optional
from utils.common import (
    generate_chatcmpl_id,
    generate_system_fingerprint,
)
from utils.providers.base import RequestBody, BaseProvider
from utils.logger import provider_logger
import time
import asyncio
import os
from PyCharacterAI import get_client
from PyCharacterAI.exceptions import SessionClosedError


class CharacterAIProvider(BaseProvider):
    def __init__(self, async_client=None):
        super().__init__(async_client)
        provider_logger.info("Initializing CharacterAIProvider")
        self.token = "CHARACTER_AI_TOKEN"

        self.character_id = "CHARACTER_AI_TOKEN"
        self.client = None
        self.costs = {
            "c1.2": 0.00000009,  
        }
        self.models = list(self.costs.keys())

    async def get_client_instance(self):
        if self.client is None:
            self.client = await get_client(token=self.token)
            me = await self.client.account.fetch_me()
            print(f"Authenticated as @{me.username}")
        return self.client

    async def create_chat(self, client, character_id):
        chat, _ = await client.chat.create_chat(character_id)
        return chat

    async def send_message(self, client, chat_id, message, character_id) -> AsyncGenerator[str, None]:
        answer = await client.chat.send_message(
            character_id, chat_id, message, streaming=True
        )
        async for message in answer:
            yield message.get_primary_candidate().text

    async def openai_proxy_stream(self, messages: List[Dict]) -> AsyncGenerator[str, None]:
        client = await self.get_client_instance()
        chat = await self.create_chat(client, self.character_id)

        full_message = ""
        for message in messages:
            full_message += f"{message['role']} said: {message['content']}\n"
        full_message += "c1.2 said: "


        previous_full_response = ""
        async for chunk in self.send_message(client, chat.chat_id, full_message, self.character_id):
            new_content = chunk[len(previous_full_response):]
            previous_full_response = chunk

            openai_response_format = {
                "choices": [
                    {
                        "delta": {"role": "assistant", "content": new_content},
                        "finish_reason": None,
                    }
                ]
            }
            yield f"data: {ujson.dumps(openai_response_format)}\n\n"

        openai_response_format = {
            "choices": [{"delta": {}, "finish_reason": "stop"}]
        }
        yield f"data: {ujson.dumps(openai_response_format)}\n\n"
        yield "data: [DONE]\n\n"

    async def openai_proxy_no_stream(self, messages: List[Dict]) -> Dict:
        client = await self.get_client_instance()
        chat = await self.create_chat(client, self.character_id)

        full_message = ""
        for message in messages:
            full_message += f"{message['role']} said: {message['content']}\n"
        full_message += "c1.2 said: "

        full_response = ""
        async for chunk in self.send_message(client, chat.chat_id, full_message, self.character_id):
            full_response += chunk

        openai_response_format = {
            "choices": [
                {
                    "message": {"role": "assistant", "content": full_response},
                    "finish_reason": "stop"
                }
            ]
        }
        return openai_response_format

    async def create_chat_completions(self, body: RequestBody) -> AsyncGenerator[dict, None]:
        chatcmpl_id = await generate_chatcmpl_id()
        system_fingerprint = await generate_system_fingerprint()
        
        if not body.model in self.models:
            yield {
                "error": f"The model: {body.model} is not available",
                "model": body.model,
                "id": chatcmpl_id,
                "system_fingerprint": system_fingerprint,
            }
            return

        try:
            if body.stream:
                async for chunk in self.openai_proxy_stream(body.messages):
                    if "[DONE]" in chunk:
                        yield {
                            "id": chatcmpl_id,
                            "object": "chat.completion.chunk",
                            "created": int(time.time()),
                            "model": body.model,
                            "choices": [{
                                "index": 0,
                                "delta": {},
                                "finish_reason": "stop",
                                "content_filter_results": None
                            }],
                            "system_fingerprint": system_fingerprint,
                        }
                        
                    else:
                        try:
                          data = ujson.loads(chunk.split("data: ")[1].strip())
                          delta = data.get("choices")[0].get("delta")
                          finish_reason = data.get("choices")[0].get("finish_reason")
                          yield {
                            "id": chatcmpl_id,
                            "object": "chat.completion.chunk",
                            "created": int(time.time()),
                            "model": body.model,
                            "choices": [{
                                "index": 0,
                                "delta": delta,
                                "finish_reason": finish_reason,
                                "content_filter_results": None
                            }],
                            "system_fingerprint": system_fingerprint,
                        }
                        except Exception as e:
                              provider_logger.error(f"Error parsing chunk {chunk} with error: {str(e)}")
                              yield{
                                "error": str(e),
                                "model": body.model,
                                "id": chatcmpl_id,
                                "system_fingerprint": system_fingerprint
                              }

            else:
                response = await self.openai_proxy_no_stream(body.messages)
                yield {
                    "id": chatcmpl_id,
                    "object": "chat.completion",
                    "created": int(time.time()),
                    "model": body.model,
                    "choices": [{
                        "index": 0,
                        "message": response.get("choices")[0].get("message"),
                        "finish_reason": response.get("choices")[0].get("finish_reason"),
                        "content_filter_results": None
                    }],
                    "system_fingerprint": system_fingerprint,
                }
        except SessionClosedError:
            yield {
                "error": "Character.ai Session Closed",
                "model": body.model,
                "id": chatcmpl_id,
                "system_fingerprint": system_fingerprint,
            }
        except Exception as e:
            provider_logger.error(f"Error in chat completion {chatcmpl_id}: {str(e)}", exc_info=True)
            yield {
                "error": str(e),
                "model": body.model,
                "id": chatcmpl_id,
                "system_fingerprint": system_fingerprint,
            }
        return
