FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Default behavior: fetch institution codes.
# Override at runtime to run other scripts.
ENTRYPOINT ["python"]
CMD ["get_institutions.py"]
