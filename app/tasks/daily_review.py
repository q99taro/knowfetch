import asyncio
from datetime import datetime, timezone
from app.core.database import get_db
from app.services.telegram_sender import TelegramSender

class ReviewScheduler:
    def __init__(self):
        self.db = get_db()
        self.notifier = TelegramSender()

    async def send_daily_review(self):
        """
        從資料庫挑選「今天應該要複習」的節點 (或測試階段隨機挑一個)，
        並封裝成訊息寄送到 Telegram。
        """
        print("====== 🧠 啟動每日知識複習推播 ======")
        
        # 1. 查詢需要複習的節點 (先查找 due_date <= 現在，或是 due_date 為空的節點來測試)
        now_iso = datetime.now(timezone.utc).isoformat()
        
        try:
            # 優先找已經到期的節點 (FSRS 演算法後續會精確更新 due_date)
            res = self.db.table("nodes").select("*").lt("due_date", now_iso).limit(1).execute()
            
            # 如果沒有到期的，為了測試，我們找一個最新建立但尚未複習過 (due_date is null) 的節點
            if not res.data:
                res = self.db.table("nodes").select("*").is_("due_date", "null").order("created_at", desc=True).limit(1).execute()

            if not res.data:
                print("-> 目前資料庫中沒有知識節點可以複習。")
                return
                
            node = res.data[0]
            node_id = node['id']
            print(f"-> 挑選到複習節點：{node['title']} ({node['label']})")
            
            # 2. (選用功能) 透過圖譜關係找出相關的程式碼 (Syntax_Example)
            related_code = ""
            if node['label'] != 'Syntax_Example':
                # 在 edges 表中找尋目標是此節點，且來源是 Syntax_Example 的紀錄
                edge_res = self.db.table("edges").select("source_id").eq("target_id", node_id).eq("relation_type", "ILLUSTRATES").execute()
                if edge_res.data:
                    code_node_id = edge_res.data[0]['source_id']
                    code_res = self.db.table("nodes").select("content").eq("id", code_node_id).execute()
                    if code_res.data:
                        related_code = code_res.data[0]['content']
            
            # 3. 透過 Telegram 發送
            success = await self.notifier.send_review_message(
                node_id=str(node_id),
                node_title=node['title'],
                node_label=node['label'],
                node_content=node['content'],
                related_code=related_code
            )
            
            if success:
                print("-> 🎉 成功推送複習訊息到 Telegram！請在 Telegram 上點擊按鈕完成複習。")
                
                # 備註：現在 due_date 與狀態更新將由 Webhook 負責處理，
                # 所以推播時不再直接更新資料庫。
                
        except Exception as e:
            print(f"複習推送發生錯誤: {e}")

if __name__ == "__main__":
    scheduler = ReviewScheduler()
    asyncio.run(scheduler.send_daily_review())