FROM python:3.10-slim

# 設定環境變數強制 Python 不緩衝標準輸出 (stdout/stderr)
# 這樣 Print 與 Log 才會即時顯示在 Hugging Face Spaces 的紀錄中
ENV PYTHONUNBUFFERED=1

WORKDIR /code

COPY ./requirements.txt /code/requirements.txt

RUN pip install --no-cache-dir --upgrade -r /code/requirements.txt

COPY ./app /code/app

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "7860"]