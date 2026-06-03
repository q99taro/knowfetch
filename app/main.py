from fastapi import FastAPI, BackgroundTasks
import asyncio

# 引入我們撰寫好的排程任務
from app.tasks.pipeline import KnowledgePipeline
from app.tasks.daily_review import ReviewScheduler

app = FastAPI(
    title="KnowFetch",
    description="自動化技術知識管理與間隔重複複習系統",
    version="1.0.0"
)

@app.get("/")
def read_root():
    return {"status": "ok", "message": "KnowFetch 伺服器運作中！"}

@app.post("/trigger-pipeline", status_code=202)
async def trigger_pipeline(background_tasks: BackgroundTasks):
    """
    透過 HTTP 呼叫觸發資料爬取與圖譜建立流水線。
    使用 BackgroundTasks 以避免 HTTP Timeout，符合 Hugging Face 部署要求。
    """
    pipeline = KnowledgePipeline()
    # 將非同步函數放入背景執行
    background_tasks.add_task(run_async_wrapper, pipeline.run_daily_pipeline)
    return {"message": "Knowledge Pipeline Background Task Started"}

@app.post("/trigger-review", status_code=202)
async def trigger_review(background_tasks: BackgroundTasks):
    """
    透過 HTTP 呼叫觸發 Telegram 每日推播。
    """
    scheduler = ReviewScheduler()
    background_tasks.add_task(run_async_wrapper, scheduler.send_daily_review)
    return {"message": "Daily Review Background Task Started"}

def run_async_wrapper(coroutine_func):
    """
    輔助函數：幫助 FastAPI BackgroundTasks 正確執行 async 方法
    """
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(coroutine_func())
    loop.close()
