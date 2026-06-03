---
title: KnowFetch
emoji: 🚀
colorFrom: blue
colorTo: green
sdk: docker
pinned: false
---

## 🚀 Project Highlights (For Interviewers & Developers)

**KnowFetch** 是一個完全自動化且**零維運成本 (Zero-Cost)** 的個人化技術知識圖譜管理系統。在極度限縮的硬體與 API 額度限制下（Hugging Face 基礎方案、Gemini 嚴格的 15 RPM 請求上限），本專案展示了如何透過強健的工程架構設計、非同步並行處理機制，以及複合式 NLP 策略，穩定且高可用地完成從海量資料挖掘 到 FSRS 演算法推播 的端到端 (End-to-End) 數據管線。

### ✨ 核心工程設計與權衡 (Engineering Trade-offs & Architecture)

面試官您可以從以下三個專案開發的重大決策中，看出本系統在「穩定度、成本、精準度」上的架構思維：

1. **圖譜關聯資料庫的降維打擊 (Logical Graph on PostgreSQL)**
   - **Why not Neo4j?** 為了符合無伺服器 (Serverless) / 零成本，並為未來的 RAG 向量搜尋鋪路。本專案選擇「不額外建置」圖形資料庫如 Neo4j，而是將知識圖譜的拓撲結構 (Topology) 映射至 Supabase (PostgreSQL) 中。
   - 利用關聯式資料表的 `Nodes` 與 `Edges` 表，透過外鍵與 SQL `JOIN` 實現了邏輯上的節點巡遊。不僅節省雙資料庫的維護負擔，亦能在未來無縫銜接 `pgvector`。

2. **複合式 NLP 萃取 (Hybrid LLM-Regex Extraction)**
   - **Why not 100% LLM?** 如果把長篇技術文章（尤其是包含程式碼的內容）直接丟給 LLM 進行分塊，極易誘發「截斷程式碼」或產生「幻覺 (Hallucinations)」。
   - **解法**：我設計了 **Adaptive Chunking** 機制，第一層以 Python 正規表達式精準保護 Markdown ```` 程式碼區塊作為「不可分割原子」，第二層才採用 `Gemini 3.1 Flash-Lite Structured Outputs` 將文段結構化為純 JSON 圖譜節點。確保系統取出的每一行程式碼都是 100% 可編譯執行的。

3. **極限速率防禦 (Strict Rate-Limiting Pipeline)**
   - API 每分鐘限制 15 次 (RPM=15) 非常容易因非同步爬蟲而觸發 `HTTP 429` 被永久封鎖。
   - **解法**：實作了帶有 Semaphore（協程號誌）與 `asyncio.sleep` 的批次過濾器 (Batch Filter)。透過 LLM 一次判定 15 篇文章，並在每次請求前嚴格加入 5.0 秒的冷卻閥門，實現平滑化流量控制，保證流水線高可用不斷線。

### 🏗️ 系統工作流 (Architecture Workflow)

```mermaid
graph TD
    subgraph Data Ingestion
        A[RSS Feeds] -->|httpx.AsyncClient| B(Supabase Node Deduplication)
        B -->|Unique URLs| C{Gemini Batch Filter}
        C -->|Keep: True| D[Web HTML Extraction]
    end
    subgraph Data Processing
        D -->|Raw Document| E(Adaptive Chunker)
        E -->|Regex Protected Blocks| F{Gemini Structured Output}
        F -->|JSON Graph Nodes & Edges| G[(Supabase Postgres)]
    end
    subgraph Spaced Repetition (FSRS)
        G -->|Daily Check due_date| H(FSRS Engine)
        H -->|Context: Fetch Linked Code| I[Telegram API]
        I -->|Push Alert| J((User))
    end
```

### 🛠️ Tech Stack (技術棧)
- **Backend**: Python 3.10+, `FastAPI`, `asyncio`, `httpx`
- **Data Extractor**: `BeautifulSoup4`, `Regex`
- **Generative AI**: Google GenAI SDK (`Gemini 3.1 Flash-Lite`)
- **Database**: Supabase (`supabase-py`), PostgreSQL (Nodes/Edges Model)
- **Notification**: Telegram Bot API
- **Spaced Repetition**: FSRS (Free Spaced Repetition Scheduler) Algorithm

### 💻 快速啟動 (Getting Started)

**1. Clone the repository / 安裝依賴**
```bash
git clone https://github.com/yourusername/knowfetch.git
cd knowfetch
pip install -r requirements.txt
```

**2. 環境變數設定 (.env)**
請在專案根目錄下建立 `.env` 檔案，填入以下資訊：
```env
GEMINI_API_KEY=your_gemini_api_key
SUPABASE_URL=your_supabase_url
SUPABASE_KEY=your_supabase_service_role_key
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
TELEGRAM_CHAT_ID=your_telegram_chat_id
```

**3. 觸發核心模組**
```bash
# 透過 FastAPI 啟動 API 伺服器
uvicorn app.main:app --host 0.0.0.0 --port 7860 --reload

# 或直接執行對應排程腳本進行測試
python -m app.tasks.pipeline
python -m app.tasks.daily_review
```