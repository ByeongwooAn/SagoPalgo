FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 TZ=Asia/Seoul
WORKDIR /app
COPY market.py reports.py strategy.py worker.py ./
COPY trials ./trials

CMD ["python", "worker.py", "--config", "trials/2026-11-27-000660.json"]
