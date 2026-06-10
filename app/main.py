from fastapi import FastAPI, Header, HTTPException, Depends
from contextlib import asynccontextmanager
import os

# 匯入應用模組
from app.tasks.pipeline import KnowledgePipeline
from app.core.database import get_db

@asynccontextmanager
async def lifespan(app: FastAPI):
    yield

app = FastAPI(
    title="KnowFetch",
    description="自動化技術文章篩選與 Email 重點摘要系統",
    version="1.0.0",
    lifespan=lifespan
)

CRON_SECRET = os.getenv("CRON_SECRET", "default_secret")

def verify_cron_secret(x_cron_secret: str = Header(None)):
    if CRON_SECRET != "default_secret" and x_cron_secret != CRON_SECRET:
        raise HTTPException(status_code=401, detail="Unauthorized")

@app.get("/")
def read_root():
    return {"status": "ok", "message": "KnowFetch 系統運作中！"}

@app.post("/trigger-pipeline", status_code=200, dependencies=[Depends(verify_cron_secret)])
async def trigger_pipeline():
    """
    透過 HTTP 觸發每日收集與知識彙整發送信件的管線。
    """
    pipeline = KnowledgePipeline()
    await pipeline.run_daily_pipeline()
    return {"message": "Knowledge Pipeline Completed"}
