FROM python:3.13-slim

WORKDIR /app

# 1. تثبيت أدوات النظام الضرورية لبناء المكتبات الثقيلة (مثل faster-whisper و numpy و scipy)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    g++ \
    cmake \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# 2. نسخ ملف المتطلبات أولاً
COPY requirements.txt .

# 3. تحديث أداة pip وتثبيت جميع المكتبات الموجودة في الملف
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# 4. نسخ باقي ملفات المشروع
COPY . .

EXPOSE 5000

CMD ["python", "app.py"]