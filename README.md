---
title: KnowFetch
emoji: 🚀
colorFrom: blue
colorTo: green
sdk: docker
pinned: false
---

## 🚀 Project Highlights

**KnowFetch** 是一個完全自動化且**零維運成本 (Zero-Cost)** 的個人化技術知識圖譜管理系統。在硬體資源與 API 額度雙重受限的條件下（Hugging Face 基礎方案、Gemini 嚴格的 15 RPM 請求上限），本專案展示了如何透過強健的工程架構設計、非同步並行處理機制，以及複合式 NLP 策略，穩定且高可用地完成從海量資料挖掘 到 FSRS 演算法推播 的端到端 (End-to-End) 數據管線。

### 💡 這是什麼工具？實際能做什麼？ (What & How It Works)

KnowFetch 是一個幫你**「全自動消化技術長文」**的超級助理。技術開發者常常在網路上看到很棒的程式教學，收藏了卻沒時間看，或是看過就忘。這個系統能自動幫你省去閱讀長文的時間，並在你最容易忘記的時候，把精華重點直接推送到你的手機裡。

**📊 系統每天的實際運作流程：**

1. **自動巡邏與挑選**：每天早上，系統會定時前往 `Towards Data Science` 與 `KDnuggets` 等知名技術網站，以及**YouTube 技術頻道 (如李宏毅教授、Vivian等)**，收集 24 小時內最新發布的文章清單與影片字幕內容。
2. **AI 精準篩選**：收集到文章後，AI (Gemini) 會根據你的喜好（例如：只要 AI、Data Science 和 Python 教學，不要電腦視覺相關文章），自動把不相干的文章過濾掉。
3. **長文拆解與代碼保護**：針對入選的好文章，系統會下載全文，並把它切成幾段「容易消化的碎片」。過程中，含有程式碼的部分會被 Python 特殊保護，確保切出來的範例程式碼完整無缺、可以直接執行。
4. **大局觀萃取與自動翻譯**：為了避免 LLM 在處理長文時「見樹不見林」，系統會以單次最高 **60,000 字元** 的超大區塊，將整篇長文一次性餵給 AI 進行全局掃視。AI 扮演資深實戰專家，摒棄無實質技術細節的科普與初階語法（如 `csv`, `for-loop`），精準搜尋並提煉出文章中的「**最佳實踐 (Best Practices)**」、「效能優化寫法」以及對應的進階套件用法，並**保留完整的上下文脈絡翻譯為繁體中文**。**特別說明：原本的程式碼範例會被原樣保留，不進行翻譯，確保學習時的準確性。**
5. **到期推播複習與互動式 FSRS 反饋**：每天晚上，系統內建的「間隔重複演算法 (FSRS-Lite)」會根據您的記憶衰退曲線，計算出今天大腦該複習哪個知識點。時間一到，你的 **Telegram** 會收到一張精美的**中文深階知識卡片**，上面不僅有概念說明與 Python 程式碼，卡片底部還附有「忘記 / 困難 / 普通 / 簡單」四個互動按鈕（Inline Keyboard）。點擊後系統會透過 FastAPI Webhook 即時更新您的個人大腦記憶參數，精準排程下一次的複習時間！

### ✨ 系統設計與架構決策 (Engineering Trade-offs & Architecture)

從以下三個專案開發的系統決策中，可以體現本專案在「穩定度、成本、精準度」上的工程思維：

1. **圖譜關聯資料庫的降維打擊 (Logical Graph on PostgreSQL)**
   - **Why not Neo4j?** 為了符合無伺服器 (Serverless) / 零成本，並為未來的 RAG 向量搜尋鋪路。本專案選擇「不額外建置」圖形資料庫如 Neo4j，而是將知識圖譜的拓撲結構 (Topology) 映射至 Supabase (PostgreSQL) 中。
   - 利用關聯式資料表的 `Nodes` 與 `Edges` 表，透過外鍵與 SQL `JOIN` 實現了邏輯上的節點巡遊。不僅節省雙資料庫的維護負擔，亦能在未來無縫銜接 `pgvector`。

2. **超大上下文 NLP 萃取與在地化 (Mega-Context Extraction & Translation)**
   - **痛點**：將長篇技術文章（尤其是包含程式碼的內容）隨意切塊，極易誘發「截斷程式碼」或導致 LLM「見樹不見林」，誤把基礎套件庫（如 `import os`）當作核心知識。
   - **解法**：我設計了 **Mega-Block Adaptive Chunking** 機制，第一層以 Python 正規表達式精準保護 Markdown ```` 程式碼區塊作為「不可分割原子」，第二層將 Chunk Size 一口氣拉升至 **60,000 字元**。充分利用 `Gemini 3.1 Flash-Lite` 百萬 Token 的超大 Context Window，強迫 LLM 以「全篇視角」進行降維打擊。
   - **高階約束 (Prompt Engineering & The "Better Way" Rule)**：透過 Structured Outputs，嚴格限制 AI 只能提取 `Technology`, `Library`, `Best_Practice`, `Method`, `Syntax_Example` 標籤。設計獨特的「The Better Way Rule」，強迫 AI 尋找「最佳實踐與替代傳統寫法的進階方案」，將為什麼這樣寫更好的原因與程式碼完整打包。精確控制單篇文章提取在 3~15 個節點，並設計了「嚴格黑名單」徹底過濾基礎 I/O 操作與純理論底層抽象概念。
   - **在地化策略**：系統會要求 LLM 在提取時，將內容轉化為繁體中文，但針對 `Syntax_Example` 標籤與 `Inline Code` (如 `df.groupby()`) 則強制要求保留原始英文代碼。這解決了中文開發者閱讀外媒深度文章的語言門檻，同時確保代碼完整性。

3. **極限速率防禦 (Strict Rate-Limiting Pipeline)**
   - API 每分鐘限制 15 次 (RPM=15) 非常容易因非同步爬蟲而觸發 `HTTP 429` 被永久封鎖。
   - **解法**：實作了帶有 Semaphore（協程號誌）與 `asyncio.sleep` 的批次過濾器 (Batch Filter)。透過 LLM 一次判定 15 篇文章，並在每次請求前嚴格加入 5.0 秒的冷卻閥門，實現平滑化流量控制，保證流水線高可用不斷線。

### 🏗️ 系統工作流 (Architecture Workflow)

```mermaid
graph TD
    subgraph Data_Ingestion [Data Ingestion]
        A[RSS Feeds & YouTube] -->|httpx.AsyncClient / youtube-transcript-api| B(Supabase Node Deduplication)
        B -->|Unique URLs| C{Gemini Batch Filter}
        C -->|Keep: True| D[Web HTML / Transcript Extraction]
    end
    subgraph Data_Processing [Data Processing]
        D -->|Raw Document| E(Adaptive Chunker)
        E -->|Regex Protected Blocks| F{Gemini Structured Output}
        F -->|JSON Graph Nodes & Edges| G[(Supabase Postgres)]
    end
    subgraph Spaced_Repetition [Spaced Repetition FSRS]
        G -->|Daily Check due_date| H(FSRS Engine)
        H -->|Context: Fetch Linked Code| I[Telegram API]
        I -->|Push Alert with Buttons| J((User))
        J -->|Click: 忘記/困難/普通/簡單| K[FastAPI Webhook]
        K -->|Update Memory Parameters| G
    end
```

### 🛠️ Tech Stack (技術棧)
- **Backend**: Python 3.10+, `FastAPI`, `asyncio`, `httpx`
- **Data Extractor**: `BeautifulSoup4`, `Regex`, `youtube-transcript-api`
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
CRON_SECRET=your_custom_secret_for_api_auth
```

**3. 觸發核心模組**
```bash
# 透過 FastAPI 啟動 API 伺服器
uvicorn app.main:app --host 0.0.0.0 --port 7860 --reload

# 或直接執行對應排程腳本進行測試
python -m app.tasks.pipeline
python -m app.tasks.daily_review
```

**4. 註冊 Telegram Webhook (重要！即時回饋必備)**
為啟用卡片底下的互動按鈕，需註冊網址讓 Telegram 能將按鈕回饋送回你的伺服器。請打開瀏覽器並訪問以下網址：
`https://api.telegram.org/bot<你的TELEGRAM_BOT_TOKEN>/setWebhook?url=<你的FASTAPI伺服器HTTPS網址>/webhook/telegram`
若顯示 `"Webhook was set"`，即代表雙向綁定成功。

**5. 雲端部署與自動化排程 (Zero-Cost Deployment)**
本專案原生支援 **Hugging Face Spaces (Docker 部署)**。
為解決免費空間的休眠機制，專案內建 `.github/workflows/cron_trigger.yml`，透過 **GitHub Actions** 每天定時發送帶有 `X-Cron-Secret` 標頭的 HTTP 請求。這樣不僅能自動觸發爬蟲與推播流水線，還能順便喚醒休眠中的 HF Space 伺服器，達成真正的無伺服器全自動化體驗。
> ⚠️ **安全性提醒**：部署至雲端時，請務必將上方所有環境變數設定在伺服器後台的 **Secrets** 中（而非公開的 Variables），以防止金鑰外洩。