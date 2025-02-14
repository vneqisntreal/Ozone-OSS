import aiohttp
import time
import sqlite3
from typing import Dict, Any, Optional
from services.user_service import UserService

DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/1339042476828393512/ndWtdlUPrIDOe3mpcL_EiZIrofqWJy2JHcCMpWXBkiGWPkEwgHV0VdZ1iv_aNZsjOMZD"

def get_discord_id(api_key: str) -> Optional[str]:
    user_service = UserService()
    user = user_service.get_user_by_api_key(api_key=api_key)
    return "User ID fetching down"

async def log_chat_completion(
    user_id: str,
    input_tokens: int,
    output_tokens: int,
    execution_time: float,
    model: str,
    is_streaming: bool = False
):
    discord_id = get_discord_id(user_id)
    user_display = f"<@{discord_id}>" if discord_id else f"`{user_id}`"
    
    embed = {
        "title": f"Chat Completion Log ({'Streaming' if is_streaming else 'Non-Streaming'})",
        "color": 3447003, 
        "fields": [
            {"name": "User", "value": user_display, "inline": True},
            {"name": "Model", "value": model, "inline": True},
            {"name": "Execution Time", "value": f"{execution_time:.2f}s", "inline": True},
            {"name": "Input Tokens", "value": str(input_tokens), "inline": True},
            {"name": "Output Tokens", "value": str(output_tokens), "inline": True},
            {"name": "Total Tokens", "value": str(input_tokens + output_tokens), "inline": True},
        ],
        "timestamp": time.strftime('%Y-%m-%dT%H:%M:%S.000Z')
    }
    
    await _send_webhook({"embeds": [embed]})

async def log_image_generation(
    user_id: str,
    prompt: str,
    output_urls: list,
    model: str
):
    discord_id = get_discord_id(user_id)
    user_display = f"<@{discord_id}>" if discord_id else f"`{user_id}`"
    
    embed = {
        "title": "Image Generation Log",
        "color": 15105570, 
        "fields": [
            {"name": "User", "value": user_display, "inline": True},
            {"name": "Model", "value": model, "inline": True},
            {"name": "Prompt", "value": prompt},
            {"name": "Generated Images", "value": "\n".join([f"[Image {i+1}]({url})" for i, url in enumerate(output_urls)])}
        ],
        "timestamp": time.strftime('%Y-%m-%dT%H:%M:%S.000Z')
    }
    
    if output_urls:
        embed["thumbnail"] = {"url": output_urls[0]}
    
    await _send_webhook({"embeds": [embed]})

async def _send_webhook(payload: Dict[str, Any]):
    async with aiohttp.ClientSession() as session:
        async with session.post(DISCORD_WEBHOOK_URL, json=payload) as response:
            if response.status not in (200, 204):
                print(f"Failed to send to Discord webhook: {response.status}") 