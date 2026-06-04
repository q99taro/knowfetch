import os
import httpx
import asyncio

class TelegramSender:
    def __init__(self):
        self.bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
        self.chat_id = os.getenv("TELEGRAM_CHAT_ID")
        
        if not self.bot_token or not self.chat_id:
            raise ValueError("Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID in .env")
            
        self.api_url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"

    async def send_review_message(self, node_id: str, node_title: str, node_label: str, node_content: str, related_code: str = "") -> bool:
        """
        將抽取出來的知識節點，格式化後傳送到 Telegram，並附上回饋按鈕
        """
        # 使用 HTML 格式，因為 Telegram 的 MarkdownV2 對特殊符號的跳脫有非常嚴格的限制
        # 而我們處理的是程式碼，用 HTML 標籤 <b>, <code>, <pre> 比較不容易壞掉
        
        message = f"{node_title}\n\n"
        
        # 處理內容，簡易跳脫 HTML 特殊字元 (如 <, >, &)
        safe_content = node_content.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        message += f"📖 <b>內容：</b>\n{safe_content}\n"
        
        if related_code:
            safe_code = related_code.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            message += f"\n💻 <b>程式碼範例：</b>\n<pre><code class='language-python'>\n{safe_code}\n</code></pre>"
        
        # 建立 Inline Keyboard 按鈕供使用者刪除已熟記的知識
        reply_markup = {
            "inline_keyboard": [
                [
                    {"text": "🗑️ 已熟記 (刪除)", "callback_data": f"delete:{node_id}"}
                ]
            ]
        }
            
        payload = {
            "chat_id": self.chat_id,
            "text": message,
            "parse_mode": "HTML",
            "reply_markup": reply_markup
        }
        
        # 設定較長的超時時間，並以手動迴圈方式進行重試，加入 Exponential Backoff
        timeout_settings = httpx.Timeout(60.0, connect=30.0, read=60.0)
        max_retries = 3
        
        # 強制使用 IPv4 綁定，避免 Hugging Face Spaces 環境中 IPv6 路由黑洞導致的 ConnectTimeout
        transport = httpx.AsyncHTTPTransport(local_address="0.0.0.0")
        
        async with httpx.AsyncClient(timeout=timeout_settings, transport=transport) as client:
            for attempt in range(1, max_retries + 1):
                try:
                    # 增加 User-Agent 避免有些防火牆或防護機制阻擋
                    headers = {"User-Agent": "Knowfetch-Bot/1.0"}
                    response = await client.post(self.api_url, json=payload, headers=headers)
                    if response.status_code != 200:
                        print(f"Telegram API 傳送失敗 ({response.status_code}): {response.text}")
                        # API 錯誤不需要重試，直接離開
                        return False
                    return True
                except httpx.TimeoutException as e:
                    print(f"[Attempt {attempt}/{max_retries}] Telegram API 連線/讀取超時: {type(e).__name__} - {e}")
                except httpx.RequestError as e:
                    print(f"[Attempt {attempt}/{max_retries}] Telegram API 請求錯誤: {type(e).__name__} - {e}")
                except Exception as e:
                    print(f"[Attempt {attempt}/{max_retries}] 發生意外錯誤: {type(e).__name__} - {str(e)}")
                
                # 如果還沒到最後一次，就等待後重試
                if attempt < max_retries:
                    wait_time = 3 ** attempt  # 3s, 9s, ... 
                    print(f"--> 等待 {wait_time} 秒後重試...")
                    await asyncio.sleep(wait_time)
            
            # 若全部次數都失敗
            print("Telegram API 傳送失敗，已達最大重試次數。")
            return False
