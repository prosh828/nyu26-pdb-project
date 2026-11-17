FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    FLASK_APP=recco

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 5000
# 시작할 때마다 관리자 계정 확인(없으면 생성) 후 개발 서버 실행
CMD ["sh", "-c", "flask ensure-admin && exec flask run --host=0.0.0.0 --port=5000 --debug"]
