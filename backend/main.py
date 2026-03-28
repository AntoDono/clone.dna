import logging
import threading
from contextlib import asynccontextmanager

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from db import db, init_db
from trainer import warmup_model
from routes import teams_router, candidates_router, clone_dna_router, build_router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    # Download the HF base model in the background so it's cached before the
    # first clone-dna request arrives — server starts immediately regardless.
    threading.Thread(target=warmup_model, daemon=True, name="hf-warmup").start()
    logger.info("HF model warmup started in background thread.")
    yield
    if not db.is_closed():
        db.close()


app = FastAPI(title="Clone.dna API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(teams_router)
app.include_router(candidates_router)
app.include_router(clone_dna_router)
app.include_router(build_router)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
