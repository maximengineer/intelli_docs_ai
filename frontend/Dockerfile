FROM python:3.13-slim

WORKDIR /app

RUN pip install --no-cache-dir streamlit==1.58.0 requests==2.34.2

COPY frontend /app/frontend

ENV INTELLIDOCS_API_URL=http://backend:8000
EXPOSE 8501

CMD ["streamlit", "run", "frontend/streamlit_app.py", "--server.address", "0.0.0.0", "--server.port", "8501"]
