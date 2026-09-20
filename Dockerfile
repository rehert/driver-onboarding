FROM python:3.13-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN python manage.py collectstatic --noinput
CMD ["sh", "-c", "python manage.py migrate --noinput && gunicorn driver_project.wsgi:application --bind 0.0.0.0:$PORT"]
