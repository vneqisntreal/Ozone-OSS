from pydantic import BaseModel

class ChatCompletionRequest(BaseModel):
    model: str
    messages: list
    max_tokens: int | None = None
    temperature: float | None = None
    stream: bool | None = False
    top_p: float | None = None
    n: int | None = 1
    stop: str | list[str] | None = None
    presence_penalty: float | None = 0
    frequency_penalty: float | None = 0