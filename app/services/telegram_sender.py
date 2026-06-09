import os
import httpx
import asyncio
import re

class TelegramSender:
    def __init__(self):
        self.bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
        self.chat_id = os.getenv("TELEGRAM_CHAT_ID")
        
        if not self.bot_token or not self.chat_id:
            raise ValueError("Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID in .env")
            
        self.api_url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"

    def _format_markdown(self, text: str) -> str:
        """
        將 Markdown 格式轉為 Telegram HTML 格式
        處理粗體、行內程式碼與多行程式碼塊，並確保標籤不會互相干擾。
        """
        if not text:
            return ""
            
        # 1. 先處理特殊字元跳脫 (這是基礎)
        # 注意：順序很重要，先換 & 再換 < >，避免之後插入的 HTML 標籤被跳脫
        text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        
        # 2. 暫存多行程式碼 ```python ... ``` -> 佔位符
        code_blocks = []
        def save_code_block(match):
            code_content = match.group(1).strip("\n")
            code_blocks.append(code_content)
            return f"___BLOCK_CODE_{len(code_blocks)-1}___"
        
        text = re.sub(r"```(?:\w+)?\n?([\s\S]*?)```", save_code_block, text)
        
        # 3. 暫存行內程式碼 `code` -> 佔位符
        inline_codes = []
        def save_inline_code(match):
            inline_content = match.group(1)
            inline_codes.append(inline_content)
            return f"___INLINE_CODE_{len(inline_codes)-1}___"
            
        text = re.sub(r"`([^`\n]+)`", save_inline_code, text)
        
        # 4. 處理粗體 **bold** -> <b>bold</b> (此時不會影響到程式碼內容)
        text = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", text)
        
        # 5. 還原多行程式碼塊 (並包裝 HTML 標籤)
        for i, code in enumerate(code_blocks):
            # Telegram HTML mode 在 <pre><code> 內不需要額外跳脫，因為我們第一步已經全域跳脫過了
            text = text.replace(f"___BLOCK_CODE_{i}___", f"<pre><code>{code}</code></pre>")
            
        # 6. 還原行內程式碼
        for i, code in enumerate(inline_codes):
            text = text.replace(f"___INLINE_CODE_{i}___", f"<code>{code}</code>")
            
        return text

    async def send_review_message(self, node_id: str, node_title: str, node_label: str, node_content: str, related_code: str = "") -> bool:
        """
        將抽取出來的知識節點，格式化後傳送到 Telegram，並附上回饋按鈕
        """
        # 使用 HTML 格式，因為 Telegram 的 MarkdownV2 對特殊符號的跳脫有非常嚴格的限制
        # 而我們處理的是程式碼，用 HTML 標籤 <b>, <code>, <pre> 比較不容易壞掉
        
        message = f"<b>{node_title}</b>\n"
        message += f"🔖 #{node_label}\n\n"
        
        # 處理內容，將 Markdown 轉為 HTML
        formatted_content = self._format_markdown(node_content)
        message += f"📖 <b>內容：</b>\n{formatted_content}\n"
        
        if related_code:
            formatted_code = self._format_markdown(related_code)
            message += f"\n💻 <b>延伸範例：</b>\n{formatted_code}"
        
        # 建立 Inline Keyboard 按鈕供使用者刪除該來源的相關知識
        reply_markup = {
            "inline_keyboard": [
                [
                    {"text": "🗑️ 略過/刪除整篇文章", "callback_data": f"delete:{node_id}"}
                ]
            ]
        }
            
        payload = {
            "chat_id": self.chat_id,
            "text": message,
            "parse_mode": "HTML",
            "reply_markup": reply_markup
        }
        
        # HF Spaces 對 api.telegram.org 的出網路不穩定：TCP 握手偶爾卡住數十秒。
        # connect timeout 設 45 秒確保握手有足夠等待時間，不會過早放棄。
        # 同時使用指數退避（5s, 15s, 45s, 90s）讓網路壅塞散去後再重試。
        timeout_settings = httpx.Timeout(60.0, connect=45.0, read=60.0)
        max_retries = 5
        
        # force_ipv4() 已於 app startup 全域套用；此處直接建立 AsyncClient 即可。
        async with httpx.AsyncClient(timeout=timeout_settings) as client:
            for attempt in range(1, max_retries + 1):
                try:
                    headers = {"User-Agent": "Knowfetch-Bot/1.0"}
                    response = await client.post(self.api_url, json=payload, headers=headers)
                    if response.status_code == 429:
                        # Telegram 速率限制：依 retry_after 等待
                        retry_after = response.json().get("parameters", {}).get("retry_after", 30)
                        print(f"[Attempt {attempt}/{max_retries}] Telegram 速率限制 (429)，等待 {retry_after} 秒後重試...")
                        await asyncio.sleep(retry_after)
                        continue
                    if response.status_code != 200:
                        print(f"Telegram API 傳送失敗 ({response.status_code}): {response.text}")
                        return False
                    return True
                except httpx.TimeoutException as e:
                    print(f"[Attempt {attempt}/{max_retries}] Telegram API 超時: {type(e).__name__}")
                except httpx.RequestError as e:
                    print(f"[Attempt {attempt}/{max_retries}] Telegram API 請求錯誤: {type(e).__name__} - {e}")
                except Exception as e:
                    print(f"[Attempt {attempt}/{max_retries}] 發生意外錯誤: {type(e).__name__} - {str(e)}")
                
                if attempt < max_retries:
                    # 指數退避：5s, 15s, 45s, 90s
                    wait_time = 5 * (3 ** (attempt - 1))
                    wait_time = min(wait_time, 90)
                    print(f"--> 等待 {wait_time} 秒後重試 (第 {attempt+1}/{max_retries} 次)...")
                    await asyncio.sleep(wait_time)
            
            print("Telegram API 傳送失敗，已達最大重試次數。")
            return False
