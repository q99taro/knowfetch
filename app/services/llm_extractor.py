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

    def summarize_article(self, article_text: str) -> str:
        """
        將「整篇文章」送交給 LLM，直接濃縮為 Markdown 格式的精要筆記。
        """
        prompt = f"""
你是一個資深的 AI 軟體架構師與技術實戰專家。你的任務是從下方的技術文本中，提煉出核心技術要點，並撰寫成一篇排版精美、結構清晰的 Markdown 筆記。

【高品質核心知識提取規範】：
1. **核心觀念 / 最佳實踐**：提取文章中的關鍵技術概念、最佳實務、效能優化建議或實用的工具教學。
2. **解釋與背景**：說明這些技術點為何重要，解決了什麼痛點。
3. **程式碼範例**：若原文有程式碼，請務必使用 Markdown 語法 (```python) 包含進來，並保留原始格式。

【排版規範】：
請將提煉出的精華透過適當的 Markdown 標題 (##, ###)、重點清單 (-) 進行排版。
每個知識點請包含：
- **情境與描述**：這段內容的基本背景與目的。
- **技術細節**：核心的技術知識點。
- **程式碼/實作**：具體的範例（如果有）。

請直接輸出你的 Markdown 筆記（請使用繁體中文）。

【文本內容】：
{article_text}
"""
        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="text/plain",
                    temperature=0.1
                ),
            )
            return response.text
        except Exception as e:
            print(f"摘要抽取失敗: {e}")
            return "無法生成摘要，解析發生錯誤。"
