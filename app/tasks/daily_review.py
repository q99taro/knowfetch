import os
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
        now_utc = datetime.now(timezone.utc)
        now_iso = now_utc.isoformat()
        
        try:
            # 優先找已經到期的節點 (FSRS 演算法後續會精確更新 due_date)
            # 根據星期決定預設推播數量：平日(週一至五) 2 個，假日(週六、日) 3 個
            default_batch = "2" if now_utc.weekday() < 5 else "3"
            batch_size = int(os.getenv("REVIEW_BATCH_SIZE", default_batch))
            
            res = self.db.table("nodes").select("*").lt("due_date", now_iso).limit(batch_size).execute()
            
            nodes_to_review = res.data if res.data else []
            
            # 如果到期節點不夠，找最新建立但尚未複習過 (due_date is null) 的節點來候補
            if len(nodes_to_review) < batch_size:
                needed = batch_size - len(nodes_to_review)
                extra_res = self.db.table("nodes").select("*").is_("due_date", "null").order("created_at", desc=True).limit(needed).execute()
                if extra_res.data:
                    nodes_to_review.extend(extra_res.data)

            if not nodes_to_review:
                print("-> 目前資料庫中沒有知識節點可以複習。")
                return
                
            for node in nodes_to_review:
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
                    print(f"-> 🎉 成功推送複習訊息：{node['title']}")
                    
                # 推送每一則訊息中間稍作停頓以免被 Telegram API 阻擋
                await asyncio.sleep(2)
                
        except Exception as e:
            import traceback
            print(f"複習推送發生錯誤: {e}")
            traceback.print_exc()

if __name__ == "__main__":
    scheduler = ReviewScheduler()
    asyncio.run(scheduler.send_daily_review())