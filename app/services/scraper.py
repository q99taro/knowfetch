import asyncio
import os
import httpx
import json
from bs4 import BeautifulSoup
from typing import List, Dict, Optional
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
import re

from urllib.parse import urlparse, parse_qs
import urllib.request
from youtube_transcript_api import YouTubeTranscriptApi

class ArticleScraper:
    FEEDS = {
        "kdnuggets": "https://www.kdnuggets.com/feed",
        "towardsdatascience": "https://towardsdatascience.com/feed/",
        "youtube_hungyi": "https://www.youtube.com/feeds/videos.xml?channel_id=UC2ggjtuuWvxrHHHiaDH1dlQ",
        "youtube_vivian": "https://www.youtube.com/feeds/videos.xml?channel_id=UCyB2RBqKbxDPGCs1PokeUiA"
    }

    async def fetch_latest_articles(self) -> List[Dict[str, str]]:
        """
        一次取得多個來源的最新文章 (24 小時內)。
        """
        all_articles = []
        now_utc = datetime.now(timezone.utc)
        one_day_ago = now_utc - timedelta(days=1)
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept-Language": "en-US,en;q=0.9",
        }
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True, headers=headers) as client:
            for source_name, url in self.FEEDS.items():
                print(f"正在擷取: {source_name}")
                try:
                    if 'youtube.com' in url:
                        # YouTube 容易遇到 TLS 握手被阻擋 (UNEXPECTED_EOF_WHILE_READING)，改使用 YouTube API v3
                        api_key = os.getenv("YOUTUBE_API_KEY")
                        if not api_key:
                            print(f"警告: 尚未設定 YOUTUBE_API_KEY，跳過 YouTube ({source_name})")
                            continue
                        
                        parsed = urlparse(url)
                        qs = parse_qs(parsed.query)
                        channel_id = qs.get('channel_id', [None])[0]
                        if not channel_id or not channel_id.startswith('UC'):
                            continue
                            
                        # 將 Channel ID (UC...) 轉成 Uploads Playlist ID (UU...)，每次 Query 只需 1 Quota
                        playlist_id = 'UU' + channel_id[2:]
                        api_url = f"https://www.googleapis.com/youtube/v3/playlistItems?part=snippet&playlistId={playlist_id}&maxResults=10&key={api_key}"
                        
                        yt_resp = await client.get(api_url)
                        yt_resp.raise_for_status()
                        yt_data = yt_resp.json()
                        
                        for item in yt_data.get('items', []):
                            snippet = item.get('snippet', {})
                            title = snippet.get('title', '')
                            video_id = snippet.get('resourceId', {}).get('videoId', '')
                            link = f"https://www.youtube.com/watch?v={video_id}"
                            abstract = snippet.get('description', '')[:500]
                            pub_date_str = snippet.get('publishedAt', '')
                            
                            try:
                                pub_date = datetime.fromisoformat(pub_date_str.replace('Z', '+00:00'))
                            except ValueError as e:
                                print(f"無法解析時間 {pub_date_str}: {e}")
                                pub_date = now_utc
                            
                            all_articles.append({
                                "source": source_name,
                                "title": title,
                                "url": link,
                                "abstract": abstract.strip(),
                                "pub_date": pub_date.isoformat(),
                                "is_recent": pub_date >= one_day_ago
                            })
                        continue  # 處理完 YouTube 後進入下一個 loop

                    # 處理非 YouTube 的一般 RSS
                    response = await client.get(url)
                    response.raise_for_status()
                    root = ET.fromstring(response.text)
                    
                    # 處理 Atom / RSS XML
                    if root.tag.endswith('feed'):
                        ns = {'atom': 'http://www.w3.org/2005/Atom'}
                        for entry in root.findall('.//atom:entry', ns):
                            title = entry.find('atom:title', ns).text
                            link = entry.find('atom:link', ns).get('href')
                            
                            abstract = ""
                            content = entry.find('atom:content', ns)
                            if content is not None and content.text:
                                soup = BeautifulSoup(content.text, 'html.parser')
                                abstract = soup.get_text(separator=' ').strip()[:500]
                                
                            pub_date_str = entry.find('atom:published', ns).text
                            try:
                                pub_date = datetime.fromisoformat(pub_date_str)
                            except ValueError as e:
                                print(f"無法解析時間 {pub_date_str}: {e}")
                                pub_date = now_utc

                            all_articles.append({
                                "source": source_name,
                                "title": title,
                                "url": link,
                                "abstract": abstract.strip(),
                                "pub_date": pub_date.isoformat(),
                                "is_recent": pub_date >= one_day_ago
                            })
                    else:
                        for item in root.findall('.//item'):
                            title = item.find('title').text
                            link = item.find('link').text
                            
                            # 解析摘要 (過濾掉 HTML 標籤)
                            description_node = item.find('description')
                            abstract = ""
                            if description_node is not None and description_node.text:
                                soup = BeautifulSoup(description_node.text, 'html.parser')
                                abstract = soup.get_text(separator=' ').strip()
                                
                            # 解析時間
                            pub_date_str = item.find('pubDate').text
                            try:
                                # KDnuggets & Medium RSS pubDate 格式通常是: "Wed, 03 Jun 2026 12:00:00 +0000" 或 "GMT"
                                if pub_date_str.endswith('GMT'):
                                    pub_date_str = pub_date_str.replace('GMT', '+0000')
                                pub_date = datetime.strptime(pub_date_str, "%a, %d %b %Y %H:%M:%S %z")
                            except ValueError as e:
                                print(f"無法解析時間 {pub_date_str}: {e}")
                                pub_date = now_utc

                            if pub_date >= one_day_ago:
                                all_articles.append({
                                    "source": source_name,
                                    "title": title,
                                    "url": link,
                                    "abstract": abstract,
                                    "pub_date": pub_date.isoformat(),
                                    "is_recent": True
                                })
                            else:
                                all_articles.append({
                                    "source": source_name,
                                    "title": title,
                                    "url": link,
                                    "abstract": abstract,
                                    "pub_date": pub_date.isoformat(),
                                    "is_recent": False
                                })
                except Exception as e:
                    import traceback
                    print(f"擷取 {source_name} 發生錯誤: {e}")
                    print(traceback.format_exc())
                    
        return all_articles

    async def fetch_article_content(self, url: str, source: str) -> str:
        """
        依據網址來源抓取文章，並遵守該網站的禮貌限制 (例如 TDS 停留 10 秒)。
        將 HTML 轉為純文字，保留 Markdown 程式碼區塊以便分塊。
        """
        if source.startswith("youtube"):
            print(f"正在抓取 YouTube 字幕: {url}")
            # parse video ID
            parsed_url = urlparse(url)
            video_id = ""
            if parsed_url.hostname in ('youtu.be', 'www.youtu.be'):
                video_id = parsed_url.path[1:]
            elif parsed_url.hostname in ('youtube.com', 'www.youtube.com'):
                if parsed_url.path == '/watch':
                    qs = parse_qs(parsed_url.query)
                    video_id = qs.get('v', [''])[0]
                    
            if not video_id:
                print(f"無法解析 YouTube Video ID: {url}")
                return ""
            
            try:
                # 嘗試抓取繁中、簡中、或英文的字幕
                try:
                    # 舊版 YouTubeTranscriptApi (例如 v0.x)
                    if hasattr(YouTubeTranscriptApi, 'get_transcript'):
                        transcript = YouTubeTranscriptApi.get_transcript(video_id, languages=['zh-TW', 'zh-Hant', 'zh-Hans', 'zh', 'en'])
                        if transcript and isinstance(transcript[0], dict):
                            full_text = " ".join([entry['text'] for entry in transcript])
                        else:
                            full_text = " ".join([str(t) for t in transcript])
                    # 新版 YouTubeTranscriptApi (例如 v1.x+)
                    elif hasattr(YouTubeTranscriptApi, 'list_transcripts'):
                        # 有的過渡版本使用 list_transcripts
                        tl = YouTubeTranscriptApi.list_transcripts(video_id)
                        t = tl.find_transcript(['zh-TW', 'zh-Hant', 'zh-Hans', 'zh', 'en'])
                        transcript = t.fetch()
                        full_text = " ".join([entry['text'] for entry in transcript])
                    else:
                        transcript = YouTubeTranscriptApi().fetch(video_id, languages=['zh-TW', 'zh-Hant', 'zh-Hans', 'zh', 'en'])
                        # FetchedTranscriptSNippet object has .text
                        full_text = " ".join([snippet.text for snippet in transcript])
                except Exception as inner_e:
                    raise inner_e

                return self._clean_text(full_text)
            except Exception as e:
                import traceback
                print(f"無法抓取 YouTube 字幕 {video_id}: {e}")
                print(traceback.format_exc())
                return ""

        # --- 禮貌性延遲 ---
        if source == "towardsdatascience":
            print(f"進入 Towards Data Science 前，強制等待 10 秒: {url}")
            await asyncio.sleep(10)
        else:
            print(f"正在抓取文章: {url}")

        async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
            # 加入 User-Agent，避免被部分網站擋掉
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
            response = await client.get(url, headers=headers)
            
            if response.status_code != 200:
                print(f"無法抓取 {url} (HTTP {response.status_code})")
                return ""
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # --- 處理程式碼轉換 ---
            for pre in soup.find_all(['pre', 'code']):
                if pre.name == 'code' and pre.parent.name == 'pre':
                    continue
                code_text = pre.get_text()
                markdown_code = f"\n\n```python\n{code_text}\n```\n\n"
                pre.replace_with(BeautifulSoup(markdown_code, 'html.parser'))
                
            for p in soup.find_all('p'):
                p.append("\n\n")

            # --- 尋找主體與抽取內文 ---
            if source == "kdnuggets":
                content_div = soup.select_one('div#post-, div.post-content, div.entry-content')
            elif source == "towardsdatascience":
                # Medium 文章有很多 section 或 article 標籤
                content_div = soup.select_one('article')
                if not content_div:
                    # Fallback: 將所有的 h1, h2, p 合併
                    elements = soup.find_all(['h1', 'h2', 'h3', 'p'])
                    content = "\n\n".join([el.get_text() for el in elements])
                    return self._clean_text(content)
            else:
                content_div = soup.body

            if not content_div:
                return ""

            return self._clean_text(content_div.get_text(separator=' '))

    def _clean_text(self, text: str) -> str:
        # 清理多餘的空白與換行，確保最多雙換行
        text = re.sub(r'\n{3,}', '\n\n', text)
        return text.strip()

if __name__ == "__main__":
    async def test_scraper():
        scraper = ArticleScraper()
        
        print("正在抓取 RSS...")
        articles = await scraper.fetch_latest_articles()
        
        print(f"共找到 {len(articles)} 篇 24 小時內的文章。")
        for i, art in enumerate(articles[:5]):
            print(f"{i+1}. [{art['source']}] {art['title']}")
            
        if articles:
            target_url = articles[0]['url']
            target_source = articles[0]['source']
            print("\n嘗試擷取第一篇文章內容...\n")
            
            content = await scraper.fetch_article_content(target_url, target_source)
            print("--- 文章預覽 (前 500 字) ---")
            print(content[:500] + "...")

    asyncio.run(test_scraper())
