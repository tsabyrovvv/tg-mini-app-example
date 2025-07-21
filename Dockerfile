# Dockerfile
FROM python:3.11-slim

# Устанавливаем системные зависимости
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Создаем рабочую директорию
WORKDIR /app

# Копируем requirements.txt и устанавливаем зависимости
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем код приложения
COPY . .

# Создаем директории для статических файлов
RUN mkdir -p staticfiles media

# Собираем статические файлы
RUN python manage.py collectstatic --noinput

# Применяем миграции
RUN python manage.py migrate

# Открываем порт
EXPOSE 8000

# Запускаем Gunicorn
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "2", "--timeout", "60", "telegram_miniapp.wsgi:application"]
