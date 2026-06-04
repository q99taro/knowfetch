import asyncio
from typing import List, Dict, Any
from app.services.scraper import ArticleScraper
from app.services.chunker import AdaptiveChunker
from app.services.llm_extractor import LLMExtractor
from app.core.database import get_db

class KnowledgePipeline:
    def __init__(self):
        self.scraper = ArticleScraper()
        self.chunker = AdaptiveChunker()
        self.llm_extractor = LLMExtractor()
        self.db = get_db()
        
        # 嚴格的速率限制：Gemini RPC=15 (每分鐘15次)，相當於每4秒只能發送1次請求
        # 我們設定為 5 秒，確保絕對不會觸發 HTTP 429
        self.gemini_rate_limit_delay = 5.0 

    async def run_daily_pipeline(self):
        print("====== 🚀 啟動 KnowFetch 每日知識網羅流水線 ======")
        
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
        # 步驟 2：資料庫去重 (Deduplication)
        # ---------------------------------------------------------
        print("[Step 2] 檢查資料庫是否已存在這些文章...")
        urls = [art['url'] for art in raw_articles]
        
        try:
            # 查詢 supabase 裡的 nodes 表，看 source_url 是否已經存在
            response = self.db.table("nodes").select("source_url").in_("source_url", urls).execute()
            existing_urls = {row['source_url'] for row in response.data}
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
        print("[Step 3] 呼叫 Gemini 進行文章價值評估...")
        filtered_articles = self.llm_extractor.batch_filter_articles(new_articles)
        print(f"-> Gemini 篩選完畢，共 {len(filtered_articles)} 篇文章符合標準。")

        # 剛呼叫完 LLM，強制暫停等待速率冷卻
        await asyncio.sleep(self.gemini_rate_limit_delay)

        # ---------------------------------------------------------
        # 步驟 4 ~ 6：逐篇抓取、切塊、抽圖譜與寫入 DB
        # ---------------------------------------------------------
        for i, article in enumerate(filtered_articles):
            print(f"\n[{i+1}/{len(filtered_articles)}] 開始處理: {article['title']}")
            
            # Step 4: 抓取全文 HTML 轉 Markdown Text
            content_text = await self.scraper.fetch_article_content(article['url'], article['source'])
            if not content_text:
                print("-> 無法擷取文章內容，跳過。")
                continue
                
            # Step 5: 自適應分塊 (Adaptive Chunking)
            chunks = self.chunker.chunk_article(content_text)
            print(f"-> 文章成功切割為 {len(chunks)} 個安全區塊。")
            
            # Step 6: 針對每個 Chunk 呼叫 LLM 抽取知識圖譜
            for c_idx, chunk in enumerate(chunks):
                print(f"  -> 處理 Chunk {c_idx+1}/{len(chunks)} ... (等待 Gemini 冷卻 5 秒)")
                
                # [重要防禦] 為了不觸發 HTTP 429 Too Many Requests，這裡強制 sleep
                await asyncio.sleep(self.gemini_rate_limit_delay)
                
                graph_data = self.llm_extractor.extract_knowledge_graph(chunk)
                if not graph_data or not graph_data.nodes:
                    print("     -> 該區塊未擷取到有效知識，跳過。")
                    continue
                
                print(f"     -> 成功抽取出 {len(graph_data.nodes)} 個節點與 {len(graph_data.edges)} 條邊，準備寫入 Supabase...")
                self.save_graph_to_db(graph_data, article['url'])

        print("====== 🎉 今日流水線執行完畢 ======")

    def save_graph_to_db(self, graph, source_url: str):
        """
        將抽取的 Graph 寫入 Supabase Postgres 關聯式表中。
        遇到相同的 (label, title) 會重複使用以防產生孤立節點。
        """
        id_mapping = {}
        
        # 1. 寫入 Nodes
        for node in graph.nodes:
            # 查詢是否已經存在同樣 title & label 的節點
            res = self.db.table("nodes").select("id").eq("label", node.label.value).eq("title", node.title).execute()
            if res.data:
                db_id = res.data[0]['id']
            else:
                new_node = {
                    "label": node.label.value,
                    "title": node.title,
                    "content": node.content,
                    "source_url": source_url,
                    # 初始化 FSRS 參數：難度=0代表剛開始，穩定度=0
                    "difficulty": 0.0,
                    "stability": 0.0,
                    "retrievability": 0.0,
                    "due_date": None  # 您可以後續排程再把時間補上，或是現在抓 UTC 時間
                }
                inserted = self.db.table("nodes").insert(new_node).execute()
                db_id = inserted.data[0]['id']
            
            # 建立關聯 (本地 ID -> 資料庫真實 UUID) 對照表
            id_mapping[node.local_id] = db_id
            
        # 2. 寫入 Edges
        for edge in graph.edges:
            src_id = id_mapping.get(edge.source_local_id)
            tgt_id = id_mapping.get(edge.target_local_id)
            
            if src_id and tgt_id:
                # 檢查 DB 是否已經有這條關係
                res = self.db.table("edges").select("id")\
                    .eq("source_id", src_id)\
                    .eq("target_id", tgt_id)\
                    .eq("relation_type", edge.relation_type.value).execute()
                
                if not res.data:
                    self.db.table("edges").insert({
                        "source_id": src_id,
                        "target_id": tgt_id,
                        "relation_type": edge.relation_type.value
                    }).execute()
if __name__ == "__main__":
    pipeline = KnowledgePipeline()
    asyncio.run(pipeline.run_daily_pipeline())