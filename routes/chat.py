from fastapi import FastAPI, HTTPException, Request
from config import API_VERSION
from fastapi.responses import StreamingResponse, JSONResponse
import httpx
import json
import time
from duckduckgo_search import DDGS
from services.user_service import UserService, UserNotFoundError, DatabaseError
from utils.token_utils import reset_daily_tokens, calculate_tokens
from utils.streaming_utils import completion_streamer
from utils.auth_utils import validate_user_auth
from utils.provider_utils import initialize_providers
from utils.discord_logger import log_chat_completion
from utils.base import ChatCompletionRequest
from utils.logger import chat_logger
import uuid

with open("data/plans.json", "r") as f:
    plans = json.loads(f.read())

def create_error_response(error_message: str, model: str, timestamp: int = None):
    if timestamp is None:
        timestamp = int(time.time())
    
    return {
        "id": str(uuid.uuid4()),
        "object": "chat.completion",
        "created": timestamp,
        "model": model,
        "choices": [{
            "message": {"role": "assistant", "content": error_message},
            "index": 0,
            "finish_reason": "stop"
        }],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    }

def get_output_length(response: dict) -> int:
    if 'choices' in response and response['choices']:
        output_length = len(response['choices'][0]['message'].get('content', ''))
        if 'function_call' in response['choices'][0]['message']:
            function_call = response['choices'][0]['message']['function_call']
            output_length += len(function_call.get('name', ''))
            output_length += len(function_call.get('arguments', ''))
        return output_length
    elif 'content' in response:
        return len(response.get('content', ''))
    return 0


def create_chat_routes(app: FastAPI, providers: dict, client: httpx.AsyncClient):
    user_service = UserService() 

    @app.post("/v1/chat/completions")
    async def chat_completions(request: ChatCompletionRequest, http_request: Request):
        request_id = str(uuid.uuid4())
        chat_logger.info(f"Request {request_id}: Starting chat completion request for model {request.model}")
        
        try:
            start_time = time.time()
            
            model = request.model
            chat_logger.info(f"Request {request_id}: Processing model {model}")

            with open("data/restricted_models.json", "r") as f:
                restricted_models = json.loads(f.read())
            
            if model in restricted_models.get("restricted_models", {}):
                user_id = http_request.headers.get("Authorization", "").split(" ")[1]
                user_data = user_service.get_user_by_api_key(user_id)
                if user_data is None:
                    return JSONResponse(content={
    "error": {
        "status": "Failed",
        "message": "Invalid API key",
        "hint": "Check your API key and try again.",
        "url": f"/{API_VERSION}/chat/completions",
        "api_version": API_VERSION
    }
}, status_code=401)
                plan_name = user_data["plan"]
                allowed_plans = restricted_models["restricted_models"][model]
                if plan_name not in allowed_plans:
                    return JSONResponse(content={
    "error": {
        "status": "Failed",
        "message": f"Model {model} is not available for your current plan.",
        "hint": "Upgrade your plan or choose a different model.",
        "url": "/v1/chat/completions",
        "api_version": API_VERSION
    }
}, status_code=403)

            def perform_duckduckgo_search(query: str) -> list:
                ddgs = DDGS()
                results = ddgs.text(query, max_results=5)
                return [
                    {
                        "title": result.get("title", ""),
                        "url": result.get("href", ""),
                        "body": result.get("body", "")
                    }
                    for result in results
                ]

            providers = initialize_providers(async_client=client, provider_directory="providers")
            forced_provider = None
            if ":web" in model:
                search_query = " ".join(msg['content'] for msg in request.messages)
                search_results = perform_duckduckgo_search(search_query)
                request.messages.append({
                    "role": "system",
                    "content": f"Web search results: {search_results}"
                })
                request.model = model.replace(":web", "")

            for provider_id, provider in providers.items():
                if "@" in model and model.split("@")[0] == provider_id:
                    model_name = model.split("@")[1]
                    if model_name not in provider.models:
                        chat_logger.error(f"Request {request_id}: Invalid model {model_name} for provider {provider_id}")
                        return JSONResponse(content={
    "error": {
        "status": "Failed",
        "message": f"Provider {provider_id} does not support model {model_name}",
        "hint": "Check the provider and model name.",
        "url": "/v1/chat/completions",
        "api_version": API_VERSION
    }
}, status_code=404)
                    forced_provider = provider
                    request.model = model_name
                    break
            
            providers = initialize_providers(async_client=client, provider_directory="providers")
            provider = forced_provider or next(
                (p for p in providers.values() if request.model in p.models), None
            )
            if not provider:
                chat_logger.error(f"Request {request_id}: No provider found for model {request.model}")
                return JSONResponse(content={
    "error": {
        "status": "Failed",
        "message": "Model not found",
        "hint": "Ensure the model name is correct.",
        "url": "/v1/chat/completions",
        "api_version": API_VERSION
    }
}, status_code=404)


            user_id = http_request.headers.get("Authorization", "").split(" ")[1]
            
            chat_logger.info(f"Request {request_id}: Authenticated user {user_id}")
            
            try:
                 user_data = user_service.get_user_by_api_key(user_id)
                 if user_data is None:
                    raise HTTPException(status_code=401, detail="Invalid API key")
                 if user_data.get('daily_token_expiration') is None or time.time() >= user_data['daily_token_expiration']:
                    reset_daily_tokens()
                    user_data = user_service.get_user_by_api_key(user_id)

                 plan_name = user_data["plan"]
                 plan = plans.get(plan_name, plans['default'])

                 user_tokens = user_data['current_tokens']
                 for limit_type, limit_value in [('rpm', 'RPM'), ('rph', 'RPH'), ('rpd', 'RPD')]:
                     if user_tokens > plan[limit_type]:
                       return JSONResponse(content={
    "error": {
        "status": "Out of Quota",
        "message": f"{limit_value} Limit Exceeded.",
        "hint": "Reduce your request rate or upgrade your plan.",
        "url": "/v1/chat/completions",
        "api_version": API_VERSION
    }
}, status_code=429)

                 input_length = sum(len(msg['content']) for msg in request.messages)
                 completion_method = (
                    getattr(provider, 'create_chat_completions', None) or 
                    getattr(provider, 'create_translation', None)
                 )
                
                 if not completion_method:
                    return JSONResponse(content={
    "error": {
        "status": "Failed",
        "message": "No suitable completion method found for provider",
        "hint": "Check provider configuration.",
        "url": "/v1/chat/completions",
        "api_version": API_VERSION
    }
}, status_code=500)

                 if request.stream:
                    return await completion_streamer(provider, request, user_id, input_length, user_service.update_tokens, plan_name, client)
                
                 tried_providers = {provider}
                 response = None
                 while True:
                    try:
                        response = None
                        async for chunk in completion_method(request):
                           if isinstance(chunk, dict):
                                 if "error" in chunk:
                                    return JSONResponse(content={"error": chunk["error"]})
                                 response = chunk

                        if not response:
                             return JSONResponse(content={
    "error": {
        "status": "Failed",
        "message": "No response received from provider",
        "hint": "Check provider status.",
        "url": "/v1/chat/completions",
        "api_version": API_VERSION
    }
}, status_code=500)
                        
                        output_length = get_output_length(response)
                        model_multiplier = provider.costs.get(request.model, 1)
                        total_tokens_used = calculate_tokens(input_length, output_length, model_multiplier)
                        user_service.update_tokens(user_id, -total_tokens_used)
                        
                        await log_chat_completion(
                                user_id=user_id,
                                input_tokens=input_length,
                                output_tokens=output_length,
                                execution_time=time.time() - start_time,
                                model=request.model
                            )
                        
                        return JSONResponse(content=response)
                        
                    except DatabaseError as e:
                        chat_logger.error(f"Request {request_id}: Database error: {str(e)}", exc_info=True)
                        return JSONResponse(content={
                            "error": {
                                "status": "Failed",
                                "message": "A database error occurred while processing your request.",
                                "hint": "Please try again later.",
                                "url": "/v1/chat/completions",
                                "api_version": API_VERSION
                            }
                        }, status_code=500)

                    except UserNotFoundError:
                        chat_logger.error(f"Request {request_id}: Invalid API key for user {user_id}")
                        return JSONResponse(content={
                            "error": {
                                "status": "Failed",
                                "message": "Invalid API key",
                                "hint": "Check your API key and try again.",
                                "url": f"/{API_VERSION}/chat/completions",
                                "api_version": API_VERSION
                            }
                        }, status_code=401)

                    except HTTPException as e:
                        chat_logger.error(f"Request {request_id}: HTTP error: {str(e)}", exc_info=True)
                        return JSONResponse(content={
                            "error": {
                                "status": "Failed",
                                "message": e.detail,
                                "hint": "Check your API key and try again.",
                                "url": f"/{API_VERSION}/chat/completions",
                                "api_version": API_VERSION
                            }
                        }, status_code=e.status_code)

                    except Exception as e:
                        if "Attempted to access streaming response content" in str(e):
                            new_provider = select_provider(request.model, async_client=client)
                            if new_provider and new_provider not in tried_providers:
                                provider = new_provider
                                tried_providers.add(provider)
                                completion_method = (
                                    getattr(provider, 'create_chat_completions', None) or 
                                    getattr(provider, 'create_translation', None)
                                )
                                continue

                        return JSONResponse(content={
    "error": {
        "status": "Failed",
        "message": str(e),
        "hint": "An unexpected error occurred.",
        "url": "/v1/chat/completions",
        "api_version": API_VERSION
    }
}, status_code=500)
                        
            except UserNotFoundError:
                chat_logger.error(f"Request {request_id}: Invalid API key for user {user_id}")
                raise HTTPException(status_code=401, detail="Invalid API key")
            except DatabaseError as e:
                chat_logger.error(f"Request {request_id}: Database error: {str(e)}")
                raise HTTPException(status_code=500, detail=str(e))
            

        except Exception as e:
            chat_logger.error(f"Request {request_id}: Fatal error: {str(e)}", exc_info=True)
            return JSONResponse(content={
    "error": {
        "status": "Failed",
        "message": "An internal server error occurred while processing your request.",
        "hint": "Please try again later.",
        "url": "/v1/chat/completions",
        "api_version": API_VERSION
    }
}, status_code=500)
