FROM python:3.11-slim

# Установка зависимостей
WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

# Копирование исходного кода
COPY . .

# Экспорт переменных среды, можно убрать если используешь .env или задаешь через Render
ENV PORT=8000
EXPOSE 8000

CMD ["python", "bot.py"]