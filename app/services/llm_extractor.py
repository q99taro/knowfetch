import json
import os
from enum import Enum
from typing import List, Dict, Any, Optional
from google import genai
from google.genai import types
from pydantic import BaseModel, Field

# -----------------
# 批次過濾的 Schema
# -----------------
class ArticleFilterResult(BaseModel):
    url: str = Field(description="文章的 URL")
    keep: bool = Field(description="是否符合爬取條件 (true/false)")
    reason: str = Field(description="判斷原因 (簡短一行)")

class BatchFilterResponse(BaseModel):
    results: List[ArticleFilterResult] = Field(description="文章過濾結果陣列")

# -----------------
# 知識圖譜的 Schema
# -----------------
class NodeLabel(str, Enum):
    Technology = "Technology"
    Library = "Library"
    Best_Practice = "Best_Practice"
    Method = "Method"
    Syntax_Example = "Syntax_Example"

class EdgeRelation(str, Enum):
    BELONGS_TO = "BELONGS_TO"
    IMPLEMENTS = "IMPLEMENTS"
    ILLUSTRATES = "ILLUSTRATES"

class KnowledgeNode(BaseModel):
    local_id: str = Field(description="局部唯一識別碼，例如 'node_1'")
    label: NodeLabel = Field(description="節點標籤")
    title: str = Field(description="快速理解這個節點的標題。必須包含技術上下文，明確標示所屬的語言、框架或模組(如 'Python open() 的 x 模式', 'Pandas Adaptive Chunking')")
    content: str = Field(description="必須是獨立且完整的知識內容：包含「發生情境」、「解決痛點」、「為什麼這樣寫更好」，並在最終附上具體的 Markdown 程式碼範例。絕對不能只有純程式碼或純定義。")

class KnowledgeEdge(BaseModel):
    source_local_id: str = Field(description="來源節點的 local_id")
    target_local_id: str = Field(description="目標節點的 local_id")
    relation_type: EdgeRelation = Field(description="關係類型")

class KnowledgeGraph(BaseModel):
    nodes: List[KnowledgeNode]
    edges: List[KnowledgeEdge]

class LLMExtractor:
    def __init__(self):
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("Missing GEMINI_API_KEY")
        
        self.client = genai.Client(api_key=api_key)
        self.model_name = "gemini-3.1-flash-lite"

        
    def batch_filter_articles(self, articles: List[Dict[str, str]]) -> List[Dict[str, Any]]:
        """
        批次將文章的 title 與 abstract 送交給 Gemini API 判斷是否應該抓取。
        返回符合條件的文章列表。
        """
        if not articles:
            return []

        prompt = """
你是專業的 AI 技術編輯，專門為「正在深化基礎並對接實戰應用的 AI 工程師」篩選具備學習與實用價值的技術文章。請根據以下文章的「標題 (Title)」與「摘要 (Abstract)」進行嚴格過濾。

【核心篩選原則】：
保留具備「實務工程落地價值、程式碼實作、基礎至進階工具教學、或生產環境經驗」的文章。允許特定工具（如 Docker, PyTorch）的基礎教學，但拒絕毫無實質技術細節的科普概念定義。

【符合條件（必須保留 keep: true）】：
1. Docker 基礎與實務應用：包含 Docker 基礎概念、常用指令教學（如 docker run, docker build）、如何編寫基礎 Dockerfile 將 Python 應用或 FastAPI 服務容器化、多階段構建（Multi-stage builds）入門。
2. PyTorch 基礎與深度學習實作：包含 PyTorch Tensors（張量）基礎操作、自動微分（Autograd）原理、如何使用 torch.nn 建立基礎神經網路、模型訓練流程（Training loop: backward, step）教學。
3. AI 與資料科學實戰：進階 Python/Pandas 資料處理技巧、高併發資料流水線優化、LLM/NLP/RAG 架構調優與技術細節。
4. 技術職涯與架構思維建議：中高階技術人員的經驗分享與職涯升級建議。
5. 前沿 AI 理論與學術深度解析：包含大型語言模型 (LLM) 架構剖析、深度學習演算法原理解釋（如 Transformer、RLHF 等高階學術理論），這類高品質概念可保留（特別適用於著名學者的演講或課程）。

【絕對排除（必須剔除 keep: false）】：
1. 毫無技術細節的科普名詞定義：排除任何「僅介紹概念名稱」而無實作步驟的字典式文章。例如：只用三言兩語解釋「什麼是 RAG」、「什麼是大語言模型」、「什麼是 AI Agent」的科技新聞或科普簡介。
2. 純概念性與新框架底層介紹：排除對於新框架的底層設計或概念宣傳（例如：專為 LLM 推論設計的 C++ 後端引擎架構介紹、未落地的底層演算法等），這些資訊雖然相關但無法轉化為每日 Python 實戰、RAG 開發或 Data Science 的實用技能。
3. 電腦視覺與視覺處理：Computer Vision (CV)、Image Processing、Object Detection 等視覺專門領域內容（除非該內容屬於 PyTorch 基礎訓練範例，如 MNIST 手寫辨識教學，則可保留）。
4. 非技術文、蹭熱度的科技新聞、流於表面的通識或單純的產品推銷廣告。

【範例對照】：
- 保留範例 1（Docker 基礎）：
  * 標題："How to Containerize Your First FastAPI Application with Docker"
  * 摘要："A beginner-friendly guide covering Dockerfile basics, essential commands like docker build, and running your Python API inside a local container."
- 保留範例 2（PyTorch 基礎）：
  * 標題："Introduction to PyTorch Tensors and Neural Network Training"
  * 摘要："Learn the absolute basics of PyTorch, including tensor operations, computing gradients with autograd, and writing your first training loop."
- 剔除範例 1（無技術細節的名詞定義）：
  * 標題："What is Retrieval-Augmented Generation (RAG)?"
  * 摘要："An executive summary defining RAG and explaining why businesses are using it to connect LLMs with internal company data."

請回傳一個 JSON，針對每篇文章給出是否保留 (keep: true/false) 與簡短原因。
"""
        article_text = "【文章列表】\n"
        for i, art in enumerate(articles):
            article_text += f"{i+1}. URL: {art['url']}\n   Title: {art['title']}\n   Abstract: {art['abstract']}\n\n"

        prompt += article_text

        response = self.client.models.generate_content(
            model=self.model_name,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=BatchFilterResponse,
                temperature=0.0
            ),
        )

        try:
            result_data = json.loads(response.text)
            filtered_urls = [
                res['url'] for res in result_data.get('results', []) if res['keep']
            ]
            final_articles = [art for art in articles if art['url'] in filtered_urls]
            return final_articles
        except Exception as e:
            print("Gemini JSON 解析失敗:", e)
            return []

    def extract_knowledge_graph(self, chunk_text: str) -> Optional[KnowledgeGraph]:
        """
        將「自適應分塊」後的文字段落送交 給 LLM，抽出符合 Schema 的 Nodes 與 Edges。
        """
        prompt = f"""
你是一個資深的 AI 軟體架構師與技術實戰專家。你的任務是從下方的技術文本中，提煉出對「資深 AI 工程師」具備高度實作價值與複習意義的技術節點，並建立結構化的知識圖譜。

【目標讀者設定與知識門檻】：
目標讀者是「具備兩年以上經驗的資深 AI 工程師與資料科學家」。
在提取任何知識點前，請先進行自我審查：「這是一個資深 AI 工程師不知道的知識嗎？」如果該知識屬於初階常識，請絕對捨棄。

【高品質核心知識定義 (The "Better Way" Rule)】：
請優先尋找並提取文章中的「最佳實踐 (Best Practices)」、「效能優化寫法」、或「替代傳統寫法的進階方案」。
當提取這類知識時，必須將「作者的解釋（為什麼這樣寫更好、更安全、更快？解決了什麼痛點？）」與「具體的程式碼」完整打包，保留充足的前後文脈絡，拒絕孤立無援的程式碼片段。

【嚴格排除黑名單 (絕對不要擷取)】：
  1. 純理論、底層架構抽象與概念性框架介紹：絕對排除如 Pinned Memory, Bin Packing, CUDA 底層硬體調度，以及「任何僅探討底層設計與理論（例如：專為 LLM 設計的 C++ 後端引擎等）」沒有伴隨實際 Python/RAG/Data Science 開發應用的理論解釋或新聞。我們只在乎對實作寫 Code 有直接幫助的細節。
  2. Python 內建庫與基礎 I/O 操作 (極度嚴格警告)：發現任何與 `os`, `sys`, `pathlib`, `csv`, `json`, `re`, `math` 相關的檔案操作、目錄建立 (例如 `Path("output").mkdir()`)，或基礎讀寫操作，請**立刻捨棄全區塊**。這對資深工程師毫無價值！
  3. 初階 Python 通用基礎語法：絕對排除 for-loop、if-else、基本資料型態操作 (list/dict)。
  4. 毫無技術細節的通識名詞定義與缺乏上下文的短語。

【本體論 (Ontology) 限制】：
請嚴格遵守以下定義的節點與關係結構，單篇文章提取數量控制在 3 到 15 個節點，寧缺勿濫。

[節點標籤 Node Labels]:
- Technology: 核心技術生態或工具（如: Docker, PyTorch, Kubernetes）。
- Library: 進階或專用第三方函式庫（如: LlamaIndex, vLLM）。注意：嚴禁將 Python 內建庫標記為 Library。
- Best_Practice: 實務最佳實踐或架構模式。專門用於記錄「更好的寫法」或「效能優化策略」，其內容必須包含痛點描述與解決方案。
- Method: 具體的進階函數、API 接口或指令（如: torch.cuda.amp.autocast）。
- Syntax_Example: 具備實戰與複習價值的程式碼範例。

[關係類型 Relationships Edges]:
- Library —[BELONGS_TO]→ Technology
- Method —[IMPLEMENTS]→ Best_Practice
- Syntax_Example —[ILLUSTRATES]→ Method 或 Best_Practice

【翻譯與提取指令】：
1. 全局掃視與限制：請全局掃視整段文本，**只提取 3 到 15 個最精華的核心知識節點**。若文章無符合標準的高階實戰內容，可回傳空陣列，寧缺勿濫。
2. 強制脈絡與上下文保留 (Context-Awareness)：為避免產生破碎、缺乏前因後果的程式碼片段，**你提取的每一個節點內容 (`content`) 都必須是「自給自足 (Self-contained)」的完整知識卡片**。
   - 在 `content` 中必須依序寫出：① 這個知識發生在什麼實務情境？ ② 解決了什麼具體痛點或為何這樣寫更好？ ③ 附上包含原本作者情境的 Markdown 程式碼範例。
   - 絕對禁止將「純概念」與「純程式碼」拆分成兩個獨立而無上下關聯的節點。如果該知識點在原文中缺乏足夠的上下文與實戰價值，請直接捨棄，不要提取。
3. 節點的 `local_id` 欄位請使用英文技術專有名詞。
4. `title` 命名必須具備「高度上下文識別度」：絕對不能使用模糊的名詞（例如：不要只寫「使用 'x' 模式」），必須明確前綴其所屬的「語言、套件、API 或框架名稱」（例如：「Python open() 函數的 'x' 模式」）。其他解釋性欄位使用**繁體中文**深入淺出地解釋。
5. 程式碼隔離：如果是 `Syntax_Example` 標籤，必須完整保留原始 Markdown 程式碼區塊（如 ```python ... ```），且必須與上方的情境描述包裝在同一個 `content` 屬性中，絕對不可翻譯或刪減縮排。
6. 如果是在其餘標籤的內容中出現行內代碼，也請保留原始英文。

【文本內容】：
{chunk_text}
"""
        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=KnowledgeGraph,
                    temperature=0.1
                ),
            )
            # 將 Gemini 回傳的 JSON 字符串轉為 Pydantic 模型
            graph_data = KnowledgeGraph.model_validate_json(response.text)
            return graph_data
        except Exception as e:
            print(f"抽取圖譜失敗: {e}")
            return None
