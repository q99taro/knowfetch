---
title: KnowFetch
emoji: 🚀
colorFrom: blue
colorTo: green
sdk: docker
pinned: false
---

## 🚀 KnowFetch

**KnowFetch** 是一個「零維運成本」的個人化技術知識圖譜系統。它能全自動抓取技術長文並透過 YouTube API 同步優質頻道影片，利用 LLM 萃取精華並生成具備完整程式碼的知識卡片，最後透過 Telegram 與 FSRS (間隔重複) 演算法推播給你複習。在極度受限的免費雲端資源下，實作了穩定且高可用的資料管線。

---

### 📊 系統每天的實際運作流程 (Daily Workflow)

1. **RSS 自動巡邏與 YouTube API 整合**：每日定時巡邏知名技術網站 (如 **KDnuggets**、**Towards Data Science**) 的 RSS，並透過 YouTube Data API v3 精準抓取優質 YouTube 技術頻道 (如 [**Hung-yi Lee**](https://www.youtube.com/@HungyiLeeNTU)、[**陳縕儂Vivian NTU MiuLab**](https://www.youtube.com/c/VivianNTUMiuLab)) 的最新影片清單與字幕。
2. **AI 精準篩選**：利用 LLM 依據個人喜好 (如: 只保留 AI/Python 相關文章) 即時過濾掉不感興趣的雜訊。
3. **長文拆解與代碼保護**：針對優質長文，系統會自動下載全文，並使用 Python 特殊正則處理，確保切塊時「範例程式碼」的完整無缺，避免程式碼被從中截斷。
4. **大局觀萃取與翻譯**：將極大片段 (最高 60,000 字元) 餵給 AI 進行全局掃視，摒棄初階語法，精準提煉「最佳實踐 (Best Practices)」，並將上下文翻譯成繁體中文（原本的程式碼原樣保留）。
5. **動態推播與反饋**：每日根據 FSRS 排程，發送深刻的技術卡片至 Telegram。用戶可點擊卡片下方的「已熟記 (刪除)」互動按鈕，透過 FastAPI Webhook 即時更新資料庫，完成正向學習迴圈。

---

### 💡 系統設計與架構決策 (Engineering Trade-offs)

1. **Mega-Context Regex 萃取防截斷**  
   - **痛點**：隨意切塊長文常導致代碼截斷與語意破碎。
   - **解法**：以 Python Regex 鎖定保護 Code Blocks 作為「不可置換單元」，並把 Chunk Size 擴大至 60k token。強迫 LLM 以全局視角產出具備「發生情境、解決痛點、完整程式碼」的 Self-contained 獨立知識卡片。
2. **PostgreSQL 模擬邏輯圖譜 (NoSQL to RDBMS)**  
   - **理由**：為了完全零成本，且替未來的 RAG 向量搜尋 (`pgvector`) 鋪路，捨棄昂貴的圖形庫 (Neo4j)。
   - **解法**：利用 Supabase (PostgreSQL) 關聯表的外鍵與 SQL JOIN 模擬出點與邊 (Nodes/Edges) 的圖譜拓撲結構，以最低成本實現圖譜關係探索。
3. **Semaphore 併發限流防禦 (Strict Rate-Limiting)**  
   - **痛點**：免費 LLM API 擁有極嚴苛的 `15 RPM` 限制，易觸發 HTTP 429 被永久封鎖。
   - **解法**：系統底層實作了帶有 `asyncio.Semaphore` 與動態 `sleep` 冷卻佇列的非同步批次過濾器，實現平滑化的流量控制，杜絕請求中斷。
4. **Zero-Cost 全自動化流水線 (Serverless CI/CD)**  
   - **解法**：後端部署於 Hugging Face Spaces (Docker)。為破解免費容器的休眠限制，透過 GitHub Actions Cron 定時發出 HTTP 請求主動喚醒伺服器，並觸發「爬蟲 → 萃取 → 推播」管線，達成全自動且不需要人工干預的運維。

---

### 🏗️ 系統架構 (Architecture)

```mermaid
graph TD
    A[Data Ingestion: RSS/YouTube API] --> B(Supabase Deduplication)
    B --> C{Async Batch Filter}
    C --> D[Adaptive Chunker & Regex]
    D --> E{Gemini Structured Output}
    E --> F[(Supabase: Node/Edge DB)]
    F --> G(FSRS Daily Review Scheduler)
    G --> H[Telegram Bot API]
    H -->|Click: 已熟記/刪除| I[FastAPI Webhook]
    I --> F
```

### 🛠️ Tech Stack
- **Backend Core**: Python 3.10+, `FastAPI`, `asyncio`, `httpx`
- **NLP & AI**: Google GenAI SDK (`Gemini 3.1 Flash-Lite`), `Regex`, `BeautifulSoup4`
- **Database**: Supabase (`PostgreSQL`)
- **Integration**: Telegram Bot API, GitHub Actions

---

### 💻 快速啟動 (Quick Start)

```bash
git clone https://github.com/yourusername/knowfetch.git
cd knowfetch
pip install -r requirements.txt
```

設定 `.env` 變數 (`GEMINI_API_KEY`, `SUPABASE_URL`, `TELEGRAM_BOT_TOKEN`) 後啟動：

```bash
# 啟動 Webhook 伺服器
uvicorn app.main:app --host 0.0.0.0 --port 7860 --reload

# 本地手動測試管線
python -m app.tasks.pipeline
python -m app.tasks.daily_review
```
