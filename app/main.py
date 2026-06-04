from fastapi import FastAPI, BackgroundTasks, Header, HTTPException, Depends, Request
import os
import httpx

# 引入我們撰寫好的排程任務
from app.tasks.pipeline import KnowledgePipeline
from app.tasks.daily_review import ReviewScheduler
from app.core.database import get_db
from app.services.fsrs import FSRSLite

app = FastAPI(
    title="KnowFetch",
    description="自動化技術知識管理與間隔重複複習系統",
    version="1.0.0"
)

CRON_SECRET = os.getenv("CRON_SECRET", "default_secret")

def verify_cron_secret(x_cron_secret: str = Header(None)):
    if CRON_SECRET != "default_secret" and x_cron_secret != CRON_SECRET:
        raise HTTPException(status_code=401, detail="Unauthorized")

@app.get("/")
def read_root():
    return {"status": "ok", "message": "KnowFetch 伺服器運作中！"}

@app.post("/trigger-pipeline", status_code=202, dependencies=[Depends(verify_cron_secret)])
async def trigger_pipeline(background_tasks: BackgroundTasks):
    """
    透過 HTTP 呼叫觸發資料爬取與圖譜建立流水線。
    使用 BackgroundTasks 以避免 HTTP Timeout，符合 Hugging Face 部署要求。
    """
    pipeline = KnowledgePipeline()
    background_tasks.add_task(pipeline.run_daily_pipeline)
    return {"message": "Knowledge Pipeline Background Task Started"}

@app.post("/trigger-review", status_code=202, dependencies=[Depends(verify_cron_secret)])
async def trigger_review(background_tasks: BackgroundTasks):
    """
    透過 HTTP 呼叫觸發 Telegram 每日推播。
    """
    scheduler = ReviewScheduler()
    background_tasks.add_task(scheduler.send_daily_review)
    return {"message": "Daily Review Background Task Started"}

@app.post("/webhook/telegram")
async def telegram_webhook(request: Request):
    """
    接收 Telegram 的 Webhook 回傳資料 (Callback Query)
    使用者點擊卡片底下的 FSRS 按鈕時，觸發更新演算法
    """
    data = await request.json()
    
    if "callback_query" in data:
        callback_query = data["callback_query"]
        callback_data = callback_query.get("data", "")
        
        # 解析按鈕回傳的資料格式： fsrs:<rating>:<node_id>
        if callback_data.startswith("fsrs:"):
            parts = callback_data.split(":")
            if len(parts) == 3:
                _, rating_str, node_id = parts
                rating = int(rating_str)
                
                db = get_db()
                
                # 撈出該節點目前的紀錄
                res = db.table("nodes").select("*").eq("id", node_id).execute()
                if res.data:
                    node = res.data[0]
                    curr_stability = node.get("stability", 0.0)
                    curr_difficulty = node.get("difficulty", 0.0)
                    
                    # 計算新的 FSRS 參數
                    new_params = FSRSLite.calculate_next_review(rating, curr_stability, curr_difficulty)
                    
                    # 寫回資料庫
                    db.table("nodes").update({
                        "stability": new_params["stability"],
                        "difficulty": new_params["difficulty"],
                        "due_date": new_params["due_date"],
                        "retrievability": 1.0 # 剛複習完記憶力復原至 100%
                    }).eq("id", node_id).execute()
                    
                    # 準備回覆 Telegram 讓按鈕的「載入中」畫面消失，並改為已完成文字
                    chat_id = callback_query["message"]["chat"]["id"]
                    message_id = callback_query["message"]["message_id"]
                    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
                    
                    answer_url = f"https://api.telegram.org/bot{bot_token}/answerCallbackQuery"
                    edit_url = f"https://api.telegram.org/bot{bot_token}/editMessageReplyMarkup"
                    
                    async with httpx.AsyncClient() as client:
                        # 告訴 Telegram APP 已經收到回饋
                        await client.post(answer_url, json={
                            "callback_query_id": callback_query["id"],
                            "text": f"✅ 已記錄！下次複習日：{new_params['due_date'][:10]}"
                        })
                        # 移除訊息底部的按鈕，防止重複點擊
                        await client.post(edit_url, json={
                            "chat_id": chat_id,
                            "message_id": message_id,
                            "reply_markup": {"inline_keyboard": []}
                        })
                        
    return {"status": "ok"}

