import random
import string
import time

async def generate_chatcmpl_id():
    random_str = ''.join(random.choices(string.ascii_lowercase + string.digits, k=29))
    return f"chatcmpl-{random_str}"

async def generate_system_fingerprint():
    random_str = ''.join(random.choices(string.ascii_lowercase + string.digits, k=9))
    return f"fp_{random_str}"

async def format_chunk(content, chatcmpl_id, model, finish_reason, stream=True):
    if stream:
        return {
            "id": chatcmpl_id,
            "object": "chat.completion.chunk",
            "created": int(time.time()),
            "model": model,
            "choices": [{
                "index": 0,
                "delta": content,
                "finish_reason": finish_reason
            }]
        }
    else:
        return {
            "id": chatcmpl_id,
            "object": "chat.completion",
            "created": int(time.time()),
            "model": model,
            "choices": [{
                "index": 0,
                "message": content,
                "finish_reason": finish_reason
            }]
        }