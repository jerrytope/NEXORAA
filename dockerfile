FROM python:3.10-slim
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && pip install --upgrade pip
COPY . .
EXPOSE 8000

# MAKE ENTRYPOINT EXECUTABLE
RUN chmod +x /app/entrypoint.sh
ENTRYPOINT ["/app/entrypoint.sh"]
COPY entrypoint.sh ./entrypoint.sh

# COLLECT STATIC FILES
# RUN python manage.py collectstatic --noinput --clear -v 0

# ENSURE CELERY IS INSTALLED
RUN pip install --no-cache-dir celery


# EXPOSE THE PORT THAT DJANGO RUNS ON
EXPOSE 8000

# START THE EXECUTION USING THE ENTRYPOINT SCRIPT 
ENTRYPOINT ["/app/entrypoint.sh"]

# NGINX CONFIGURATION
#FROM nginx:alpine
#COPY nginx.conf /etc/nginx/nginx.conf
#EXPOSE 80
