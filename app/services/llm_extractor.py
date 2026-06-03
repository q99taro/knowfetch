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
你是專業的 AI 技術編輯。請根據以下文章的「標題 (Title)」與「摘要 (Abstract)」過濾文章。

【符合條件的文章必須包含以下領域之一】：
1. AI (尤其是 LLM / NLP)
2. Data Science (資料科學)
3. Machine Learning / Deep Learning
4. Python (尤其是和前面資料科學/AI相關的教學)
5. 針對上述領域的 Career Advice (職涯建議)

【絕對排除】：
1. Computer Vision (CV) / Image Processing / Object Detection 等視覺相關
2. 非技術文或不相干的廣告

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
你是一個知識工程師，你的任務是從下方的技術文本中，抽取出知識圖譜 (Nodes 與 Edges)。

【本體論 (Ontology) 限制】：
[節點標籤 Node Labels]:
- Technology: 技術生態 (例如: Python, LLM)
- Library: 函式庫 (例如: Pandas, PyTorch)
- Concept: 核心概念 (例如: Adaptive Chunking, DataFrame)
- Method: 具體方法或函數 (例如: read_csv(), chunk_article())
- Syntax_Example: 程式碼範例 (必須保留完整代碼)

[關係類型 Relationships Edges]:
- Library —[BELONGS_TO]→ Technology
- Method —[IMPLEMENTS]→ Concept
- Syntax_Example —[ILLUSTRATES]→ Method 或 Concept

請盡可能捕捉文本中的核心知識與程式碼範例，建立關係，確保知識可以被間隔重複引擎 (FSRS) 用來複習。
如果此段落沒有太多具體名詞，則盡量提取至少一個 Concept。

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
