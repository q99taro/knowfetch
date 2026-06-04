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
    Concept = "Concept"
    Method = "Method"
    Syntax_Example = "Syntax_Example"

class EdgeRelation(str, Enum):
    BELONGS_TO = "BELONGS_TO"
    IMPLEMENTS = "IMPLEMENTS"
    ILLUSTRATES = "ILLUSTRATES"

class KnowledgeNode(BaseModel):
    local_id: str = Field(description="局部唯一識別碼，例如 'node_1'")
    label: NodeLabel = Field(description="節點標籤")
    title: str = Field(description="快速理解這個節點的名詞標題(如 'Pandas', 'Adaptive Chunking')")
    content: str = Field(description="定義與詳細內容。若是 Syntax_Example 必須保留完整 Markdown 程式碼。")

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

【絕對排除（必須剔除 keep: false）】：
1. 毫無技術細節的科普名詞定義：排除任何「僅介紹概念名稱」而無實作步驟的字典式文章。例如：只用三言兩語解釋「什麼是 RAG」、「什麼是大語言模型」、「什麼是 AI Agent」的科技新聞或科普簡介。
2. 電腦視覺與視覺處理：Computer Vision (CV)、Image Processing、Object Detection 等視覺專門領域內容（除非該內容屬於 PyTorch 基礎訓練範例，如 MNIST 手寫辨識教學，則可保留）。
3. 非技術文、蹭熱度的科技新聞、流於表面的通識或單純的產品推銷廣告。

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
你是一個專業的 AI 技術翻譯與知識工程師。你的任務是從下方的技術文本中，抽取出知識圖譜 (Nodes 與 Edges) **並將其翻譯為繁體中文**。

【本體論 (Ontology) 限制】：
[節點標籤 Node Labels]:
- Technology: 技術生態 (例如: Python, LLM)
- Library: 函式庫 (例如: Pandas, PyTorch)
- Concept: 核心概念 (例如: Adaptive Chunking, DataFrame)
- Method: 具體方法或函數 (例如: read_csv(), chunk_article())
- Syntax_Example: 程式碼範例 (必須保留原始程式碼，不可翻譯)

[關係類型 Relationships Edges]:
- Library —[BELONGS_TO]→ Technology
- Method —[IMPLEMENTS]→ Concept
- Syntax_Example —[ILLUSTRATES]→ Method 或 Concept

【翻譯與提取指令】：
1. 所有節點的 `title` 與 `content` 欄位必須使用**繁體中文**。
2. **程式碼保留**：如果是 `Syntax_Example` 標籤，其 `content` 必須保留原始 Markdown 程式碼內容，絕對不要翻譯。
3. 如果是在其餘標籤的 `content` 中出現行內代碼 (如 `pd.read_csv()`)，也請保留原始英文。
4. 技術專有名詞若無通用的中文翻譯，可保留英文或在中文後括號備註英文。
5. 請盡可能捕捉文本中的核心知識與程式碼範例，建立關係，確保知識可以被間隔重複引擎 (FSRS) 用來複習。
6. 如果此段落沒有太多具體名詞，則盡量提取至少一個 Concept。

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
