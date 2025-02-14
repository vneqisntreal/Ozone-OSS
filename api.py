from fastapi import FastAPI
import logging
import uvicorn
from fastapi.middleware.cors import CORSMiddleware
import httpx
from utils.provider_utils import initialize_providers 
from routes.chat import create_chat_routes
from routes.models import create_model_routes
from routes.tts import router as tts_router
from routes.transcriptions import create_transcription_routes
from routes.images import router as images_router
from routes.me import router as me_router
from routes.moderations import router as moderations_router

PROVIDER_DIRECTORY = "providers"

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

logging.basicConfig(level=logging.INFO)

client = httpx.AsyncClient(timeout=150)

providers = initialize_providers(client, PROVIDER_DIRECTORY)

create_chat_routes(app, providers, client)
create_model_routes(app, providers)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8080)
