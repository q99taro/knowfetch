from fastapi import FastAPI, Header, HTTPException, Depends, Request
from contextlib import asynccontextmanager
import os
import httpx

# 匯入應用模組
from app.tasks.pipeline import KnowledgePipeline
from app.tasks.daily_review import ReviewScheduler
from app.core.database import get_db
from app.services.fsrs import FSRSLite

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 伺服器啟動時，自動向 Telegram 註冊 Webhook
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    space_host = os.getenv("SPACE_HOST") # Hugging Face Spaces 內建環境變數
    
    # 如果使用者有自行設定 WEBHOOK_URL 優先使用，否則使用 HF Space 預設網址
    webhook_url = os.getenv("WEBHOOK_URL")
    if not webhook_url and space_host:
        webhook_url = f"https://{space_host}/webhook/telegram"
        
    if bot_token and webhook_url:
        print(f"====== 正在設定 Telegram Webhook: {webhook_url} ======")
        async with httpx.AsyncClient() as client:
            try:
                res = await client.post(
                    f"https://api.telegram.org/bot{bot_token}/setWebhook",
                    json={"url": webhook_url}
                )
                print("Webhook 註冊結果:", res.text)
            except Exception as e:
                print(f"Webhook 註冊失敗: {e}")
                
    yield
    # 伺服器關閉時的清理動作 (Optional)

app = FastAPI(
    title="KnowFetch",
    description="零成本自動化技術知識圖譜與間隔重複系統",
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
    透過 HTTP 觸發每日收集與知識萃取管線。
    直接 await 執行，避免 Hugging Face Spaces 在回應後切斷 CPU 導致背景任務卡住。
    """
    pipeline = KnowledgePipeline()
    await pipeline.run_daily_pipeline()
    return {"message": "Knowledge Pipeline Completed"}

@app.post("/trigger-review", status_code=200, dependencies=[Depends(verify_cron_secret)])
async def trigger_review():
    """
    透過 HTTP 觸發 Telegram 每日推播複習。
    直接 await 執行，避免 HF Spaces 暫停容器。
    """
    scheduler = ReviewScheduler()
    await scheduler.send_daily_review()
    return {"message": "Daily Review Completed"}

@app.post("/webhook/telegram")
async def telegram_webhook(request: Request):
    """
    接收 Telegram 的 Webhook 回傳資料 (Callback Query)
    """
    data = await request.json()
    
    if "callback_query" in data:
        callback_query = data["callback_query"]
        callback_data = callback_query.get("data", "")
        bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
        
        # 1. 立即回應 Telegram，消除「加載中」轉圈圈
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                answer_url = f"https://api.telegram.org/bot{bot_token}/answerCallbackQuery"
                await client.post(answer_url, json={
                    "callback_query_id": callback_query["id"],
                    "text": "收到回饋，處理中..."
                })
        except Exception as e:
            print(f"回應Callback失敗: {e}")
        
        # 2. 處理資料庫更新 (刪除該來源所有相關紀錄並加入黑名單)
        if callback_data.startswith("delete:"):
            parts = callback_data.split(":")
            if len(parts) == 2:
                _, node_id = parts
                
                db = get_db()
                
                # 先查詢該節點的 source_url
                res = db.table("nodes").select("source_url").eq("id", node_id).execute()
                if res.data and res.data[0].get("source_url"):
                    source_url = res.data[0]["source_url"]
                    
                    # 將此 url 加入 ignored_urls 表，以防未來重複爬取
                    try:
                        db.table("ignored_urls").insert({"url": source_url}).execute()
                    except Exception as e:
                        print(f"寫入 ignored_urls 失敗 (可能已存在): {e}")

                    # 從資料庫中刪除該 source_url 的所有節點
                    db.table("nodes").delete().eq("source_url", source_url).execute()
                else:
                    # 如果找不到網址，就 fallback 刪除單筆 (確保例外安全)
                    db.table("nodes").delete().eq("id", node_id).execute()
                
                chat_id = callback_query["message"]["chat"]["id"]
                message_id = callback_query["message"]["message_id"]
                
                edit_url = f"https://api.telegram.org/bot{bot_token}/editMessageReplyMarkup"
                answer_url = f"https://api.telegram.org/bot{bot_token}/answerCallbackQuery"
                
                try:
                    async with httpx.AsyncClient(timeout=10.0) as client:
                        # 再次回應帶出 Toast 提示
                        await client.post(answer_url, json={
                            "callback_query_id": callback_query["id"],
                            "text": "✅ 已刪除！該來源所有內容已被清除並列入不爬取名單"
                        })
                        # 隱藏或清空按鈕
                        await client.post(edit_url, json={
                            "chat_id": chat_id,
                            "message_id": message_id,
                            "reply_markup": {"inline_keyboard": []}
                        })
                except Exception as e:
                    print(f"後續按鈕隱藏與提示更新失敗: {e}")
                        
    return {"status": "ok"}