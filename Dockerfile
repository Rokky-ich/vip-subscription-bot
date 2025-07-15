FROM python:3.11-slim

# Установим зависимости
RUN apt-get update && apt-get install -y gcc

# Установка рабочей директории
WORKDIR /app

# Копируем все файлы
COPY . .

# Обновим pip
RUN pip install --upgrade pip

# Установим зависимости проекта
RUN pip install -r requirements.txt

# Запускаем бота
CMD ["python", "bot.py"]