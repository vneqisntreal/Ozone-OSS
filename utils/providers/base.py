from typing import List, Dict, Optional, Union
from pydantic import BaseModel

class RequestBody(BaseModel):
    model: str
    messages: Optional[List[Dict]] = None
    input: Optional[str] = None 
    max_tokens: int = 4097
    temperature: float = 0.7
    stream: bool = False
    top_p: float = 1
    voice: Optional[str] = None  
    response_format: Optional[str] = None  
    reasoning_effort: Optional[str] = None

class Message(BaseModel):
    role: str
    content: str

class BaseProvider:
    def __init__(self, name: str):
        self.name = name
        self.models = []
        self.costs = {}

    def create_chat_completions(self, body: RequestBody):
        raise NotImplementedError

    def create_tts_completions(self, body: RequestBody):
        raise NotImplementedError
