FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

WORKDIR /app

# ติดตั้ง C dependencies สำหรับ mysqlclient และ Node.js สำหรับ django-tailwind
RUN apt-get update && apt-get install -y \
    curl \
    gcc \
    default-libmysqlclient-dev \
    pkg-config \
    && curl -fsSL https://deb.nodesource.com/setup_18.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# ติดตั้ง Python Packages
COPY requirements.txt /app/
RUN pip install --upgrade pip
RUN pip install -r requirements.txt

# คัดลอก Source Code ทั้งหมด
COPY . /app/

# Build Tailwind CSS และรวมไฟล์ Static
RUN python manage.py tailwind build --no-input || true
RUN python manage.py collectstatic --no-input

EXPOSE 8000

# รันด้วย Daphne (เนื่องจากโปรเจกต์ใช้ Channels/Daphne)

CMD ["sh", "-c", "python manage.py migrate && python -m gunicorn pos_system.wsgi:application --bind 0.0.0.0:8000"]
