import time
import logging
from fastapi import HTTPException, Request
from key_management import get_user, update_user_plan

def validate_user_auth(http_request: Request):
    auth_header = http_request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Error: Authorization header missing or invalid. Hint: Make sure you are passing an API key in 'Authorization' header. Example: 'Authorization: Bearer sk-ozone-YOUR-API-KEY'")

    api_key = auth_header.split("Bearer ")[1]
    user_id = api_key

    user = get_user(user_id)
    if not user:
        logging.info(f"User not found for API Key: {api_key}")
        raise HTTPException(status_code=401, detail="Unauthorized: User not found")
    

    if user['plan'] != 'default' and user['plan_expiration'] and time.time() > user['plan_expiration']:
        update_user_plan(user_id, 'default', None)
        user = get_user(user_id)

    if user['tokens'] < 0:
        raise HTTPException(status_code=429, detail="Not enough quota available for this request.")

    return user
