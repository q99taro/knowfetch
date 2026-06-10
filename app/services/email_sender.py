import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

class EmailSender:
    def __init__(self):
        self.smtp_server = os.getenv("SMTP_SERVER", "smtp.gmail.com")
        self.smtp_port = int(os.getenv("SMTP_PORT", "587"))
        self.sender_email = os.getenv("SMTP_EMAIL")
        self.sender_password = os.getenv("SMTP_PASSWORD")
        self.recipient_email = os.getenv("RECIPIENT_EMAIL")

    async def send_article_summary(self, title: str, article_url: str, markdown_summary: str) -> bool:
        """
        寄送單篇文章的 Markdown 總結到指定信箱。
        這裡為了保持簡單，會使用 Pymdown 等轉換工具（如果有需要）或直接以純文字/HTML寄出。
        這裡我們將 Markdown 放進 pre 或簡單的 HTML 提供排版。
        """
        if not self.sender_email or not self.sender_password or not self.recipient_email:
            print("⚠️ 未設定 SMTP_EMAIL, SMTP_PASSWORD 或 RECIPIENT_EMAIL，無法寄送 Email。")
            return False

        subject = f"[KnowFetch] 新文章重點：{title}"

        # 簡單地將 Markdown 包裝進 HTML 中，為了更好的閱讀體驗
        # (若需要轉換 markdown，可以引入 markdown 庫，但在這邊我們簡化為純內文搭配一點樣式)
        html_content = f"""
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                h1, h2, h3 {{ color: #2c3e50; }}
                pre {{ background-color: #f8f9fa; padding: 15px; border-radius: 5px; overflow-x: auto; }}
                code {{ background-color: #f8f9fa; padding: 2px 4px; border-radius: 3px; font-family: monospace; }}
                .footer {{ margin-top: 20px; font-size: 0.9em; color: #7f8c8d; border-top: 1px solid #eee; padding-top: 10px; }}
            </style>
        </head>
        <body>
            <h3>文章標題：<a href="{article_url}">{title}</a></h3>
            <hr/>
            <!-- 使用 pre-wrap 保留 Markdown 換行 -->
            <div style="white-space: pre-wrap;">{markdown_summary}</div>
            <div class="footer">
                <p>這封郵件由 KnowFetch 自動寄送。</p>
            </div>
        </body>
        </html>
        """

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = self.sender_email
        msg["To"] = self.recipient_email

        # 可以同時加上純文字與 HTML 版本
        part1 = MIMEText(markdown_summary, "plain", "utf-8")
        part2 = MIMEText(html_content, "html", "utf-8")
        msg.attach(part1)
        msg.attach(part2)

        try:
            # 這裡使用同步的 smtplib。若要在 async 中跑，我們可以把它丟進 threadpool
            server = smtplib.SMTP(self.smtp_server, self.smtp_port)
            server.starttls()
            server.login(self.sender_email, self.sender_password)
            server.sendmail(self.sender_email, self.recipient_email, msg.as_string())
            server.quit()
            return True
        except Exception as e:
            print(f"❌ 寄送 Email 失敗: {e}")
            return False
