import os
import httpx

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
        
        # 建立 Inline Keyboard 按鈕供 FSRS 收集使用者回饋
        reply_markup = {
            "inline_keyboard": [
                [
                    {"text": "🔴 忘記", "callback_data": f"fsrs:1:{node_id}"},
                    {"text": "🟠 困難", "callback_data": f"fsrs:2:{node_id}"}
                ],
                [
                    {"text": "🟢 普通", "callback_data": f"fsrs:3:{node_id}"},
                    {"text": "🔵 簡單", "callback_data": f"fsrs:4:{node_id}"}
                ]
            ]
        }
            
        payload = {
            "chat_id": self.chat_id,
            "text": message,
            "parse_mode": "HTML",
            "reply_markup": reply_markup
        }
        
        # 設定較長的超時時間 (例如 30 秒)，並加上重試邏輯
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.post(self.api_url, json=payload)
                if response.status_code != 200:
                    print(f"Telegram API 傳送失敗 ({response.status_code}): {response.text}")
                    return False
                return True
            except httpx.TimeoutException as e:
                print(f"Telegram API 連線超時或讀取超時，請檢查網路。詳細錯誤: {e}")
                return False
            except httpx.RequestError as e:
                print(f"Telegram API 請求錯誤: {e}")
                return False
            except Exception as e:
                print(f"Telegram 發送時發生意外錯誤: {type(e).__name__} - {str(e)}")
                return False
