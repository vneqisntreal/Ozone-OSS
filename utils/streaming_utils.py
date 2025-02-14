import ujson
from fastapi.responses import StreamingResponse
from utils.token_utils import calculate_tokens
from utils.discord_logger import log_chat_completion
import time

async def completion_streamer(provider, request, user_id, input_length, update_tokens_func, plan_name='default', client=None):
    output_length = 0
    tokens_deducted = False
    model_multiplier = provider.costs.get(request.model, 1)
    start_time = time.time()
    full_response = []

    async def stream_generator():
        nonlocal output_length, tokens_deducted, full_response
        try:
            async for chunk in provider.create_chat_completions(request):
                if not isinstance(chunk, dict):
                    try:
                        chunk = ujson.loads(chunk)
                    except Exception as parse_error:
                        print(f"Error parsing chunk: {parse_error}")
                        continue

                if "error" in chunk:
                    yield f"data: {ujson.dumps(chunk)}\n\n"
                    return

                yield f"data: {ujson.dumps(chunk)}\n\n"

                delta = chunk.get('choices', [{}])[0].get('delta', {})
                
                content = delta.get('content', '')
                if content:
                    output_length += len(content)
                    full_response.append(content)
                    
                if 'function_call' in delta:
                    function_call = delta['function_call']
                    if 'name' in function_call:
                        output_length += len(function_call['name'])
                        full_response.append(function_call['name'])
                    if 'arguments' in function_call:
                        output_length += len(function_call['arguments'])
                        full_response.append(function_call['arguments'])
                
            yield "data: [DONE]\n\n"
            
        except Exception as e:
            print(f"Streaming error: {e}")
            yield f"data: {ujson.dumps({'error': str(e)})}\n\n"
        
        finally:
            if not tokens_deducted:
                total_tokens_used = calculate_tokens(input_length, output_length, model_multiplier)
                update_tokens_func(user_id, -total_tokens_used)
                tokens_deducted = True
                
                if True:
                    execution_time = time.time() - start_time
                    await log_chat_completion(
                        user_id=user_id,
                        input_tokens=input_length,
                        output_tokens=output_length,
                        execution_time=execution_time,
                        model=request.model,
                        is_streaming=True
                    )

    return StreamingResponse(stream_generator(), media_type="text/event-stream")
