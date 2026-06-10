import asyncio
import traceback
from typing import List, Dict, Any
from app.services.scraper import ArticleScraper
from app.services.llm_extractor import LLMExtractor
from app.services.email_sender import EmailSender
from app.core.database import get_db

class KnowledgePipeline:
    def __init__(self):
        self.scraper = ArticleScraper()
        self.llm_extractor = LLMExtractor()
        self.email_sender = EmailSender()
        self.db = get_db()
        
        # 嚴格的速率限制：Gemini RPC=15 (每分鐘15次)，相當於每4秒只能發送1次請求
        # 我們設定為 5 秒，確保絕對不會觸發 HTTP 429
        self.gemini_rate_limit_delay = 5.0 

    async def run_daily_pipeline(self):
        print("====== 🚀 啟動 KnowFetch 每日文章重點摘要流水線 ======")
        
        # ---------------------------------------------------------
        # 步驟 1：抓取 24 小時內的所有文章清單
        # ---------------------------------------------------------
        print("[Step 1] 正在抓取網誌 RSS 與 YouTube 影片資訊...")
        raw_articles = await self.scraper.fetch_latest_articles()
        print(f"-> 共抓取到 {len(raw_articles)} 篇候選文章。")
        
        if not raw_articles:
            print("-> 今日無新文章，流水線結束。")
            return

        # ---------------------------------------------------------
        # 步驟 2：資料庫去重 (Deduplication) 依舊依賴 ignored_urls 保存已處理紀錄
        # ---------------------------------------------------------
        print("[Step 2] 檢查資料庫是否已存在這些文章...")
        urls = [art['url'] for art in raw_articles]
        
        try:
            # 我們不再對 nodes 表查詢，僅查詢 ignored_urls (已處理/已寄信/拒絕的文章)
            ignored_res = self.db.table("ignored_urls").select("url").in_("url", urls).execute()
            existing_urls = {row['url'] for row in ignored_res.data}
        except Exception as e:
            print(f"-> 資料庫查詢失敗 ({e})，為安全起見，假設全部未抓取過。")
            existing_urls = set()

        dedup_articles = [art for art in raw_articles if art['url'] not in existing_urls]
        
        # 處理各來源舊內容回退邏輯 (若當天無新內容，挑一篇尚未抓取過的舊內容)
        new_articles = []
        for source in set(art['source'] for art in dedup_articles):
            source_arts = [art for art in dedup_articles if art['source'] == source]
            
            recent_arts = [art for art in source_arts if art.get('is_recent', True)]
            if recent_arts:
                # 如果有 24 小時內的新內容，把新內容全部加入
                new_articles.extend(recent_arts)
            else:
                # 如果沒有新內容，從尚未抓取的舊內容中挑選最近的一篇
                older_arts = [art for art in source_arts if not art.get('is_recent', True)]
                if older_arts:
                    older_arts.sort(key=lambda x: x['pub_date'], reverse=True)
                    new_articles.append(older_arts[0])
                    print(f"-> [{source}] 今日無新內容，補抓一篇未處理過的舊內容: {older_arts[0]['title']}")

        print(f"-> 去重與篩選後，剩下 {len(new_articles)} 篇新文章準備過濾。")

        if not new_articles:
            print("-> 所有文章皆已處理過，流水線結束。")
            return

        # ---------------------------------------------------------
        # 步驟 3：LLM 批次判斷與篩選 (Batch Filtering)
        # ---------------------------------------------------------
        print("[Step 3] 進行文章價值評估 (YouTube 影片直接保留，其餘交由 Gemini 篩選)...")
        
        yt_articles = [art for art in new_articles if art['source'].startswith('youtube_')]
        other_articles = [art for art in new_articles if not art['source'].startswith('youtube_')]
        
        filtered_articles = []
        if yt_articles:
            print(f"-> 直接保留 {len(yt_articles)} 篇 YouTube 影片 (跳過 LLM 評估)。")
            filtered_articles.extend(yt_articles)
            
        if other_articles:
            print(f"-> 將 {len(other_articles)} 篇文章交由 Gemini 進行篩選...")
            llm_filtered = self.llm_extractor.batch_filter_articles(other_articles)
            
            # 錄入被 LLM 篩選掉的文章至 ignored_urls，避免下次流水線重複處理
            filtered_urls_set = {art['url'] for art in llm_filtered}
            rejected_urls = [art['url'] for art in other_articles if art['url'] not in filtered_urls_set]
            if rejected_urls:
                print(f"   -> 有 {len(rejected_urls)} 篇文章被 LLM 判定為不符合條件，將其加入略過清單。")
                try:
                    ignored_data = [{"url": url} for url in rejected_urls]
                    self.db.table("ignored_urls").insert(ignored_data).execute()
                except Exception as e:
                    print(f"   -> 寫入 ignored_urls 失敗 (可能已存在): {e}")

            filtered_articles.extend(llm_filtered)
            
            # 剛呼叫完 LLM，強制暫停等待速率冷卻
            await asyncio.sleep(self.gemini_rate_limit_delay)

        print(f"-> 篩選完畢，共 {len(filtered_articles)} 篇文章準備抓取與分析。")

        # ---------------------------------------------------------
        # 步驟 4 ~ 6：逐篇抓取、摘要與寄送 Email
        # ---------------------------------------------------------
        import random
        yt_articles_count = sum(1 for a in filtered_articles if a['source'].startswith('youtube'))
        if yt_articles_count > 0:
            target_time_seconds = 7200
            delay_per_yt = target_time_seconds // yt_articles_count
            yt_base_delay = max(60, min(delay_per_yt, 300))
        else:
            yt_base_delay = 60

        for i, article in enumerate(filtered_articles):
            print(f"\n[{i+1}/{len(filtered_articles)}] 開始處理: {article['title']}")
            
            # Step 4: 抓取全文 HTML 轉 Markdown Text
            content_text = await self.scraper.fetch_article_content(article['url'], article['source'])
            if not content_text:
                print("-> 無法擷取文章內容，跳過並加入忽略清單。")
                try:
                    self.db.table("ignored_urls").insert({"url": article['url']}).execute()
                except:
                    pass
                continue
                
            # Step 5: 全文呼叫 LLM 進行摘要重點提取
            print("  -> 呼叫 Gemini 進行重點摘要...")
            try:
                markdown_summary = self.llm_extractor.summarize_article(content_text)
                
                # 就算失敗或是無知識點也視為處理過
                if "無法生成摘要" in markdown_summary or "本篇文章無進階實作知識點" in markdown_summary:
                    print("  -> 該文章未提取出有意義之重點或發生錯誤，將直接略過寄件。")
                else:
                    # Step 6: 將摘要寄送至 Email
                    print("  -> 正在將重點以 Email 寄出...")
                    success = await self.email_sender.send_article_summary(
                        title=article['title'],
                        article_url=article['url'],
                        markdown_summary=markdown_summary
                    )
                    if success:
                        print("  -> 🎉 Email 寄送成功！")
                    else:
                        print("  -> ⚠️ Email 寄送失敗！")
                        
            except Exception as e:
                print(f"  -> 處理時發生異常：{e}")
                traceback.print_exc()

            # 標記為已處理 (加入 ignored_urls 避免未來重複爬取與處理)
            try:
                self.db.table("ignored_urls").insert({"url": article['url']}).execute()
            except:
                pass

            # 爬取下一篇文章前，稍微等待確保不會觸發 Rate Limit
            if i < len(filtered_articles) - 1:
                if article['source'].startswith('youtube'):
                    jitter = random.uniform(0.8, 1.2)
                    sleep_time = int(yt_base_delay * jitter)
                    print(f"-> 🍵 避免 YouTube 爬取頻繁，等待 {sleep_time} 秒...\n")
                else:
                    sleep_time = self.gemini_rate_limit_delay
                    print(f"-> 冷卻 {sleep_time} 秒...\n")
                
                await asyncio.sleep(sleep_time)

        print("====== 🎉 今日流水線執行完畢 ======")

if __name__ == "__main__":
    pipeline = KnowledgePipeline()
    asyncio.run(pipeline.run_daily_pipeline())