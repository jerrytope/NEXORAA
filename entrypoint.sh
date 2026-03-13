#!/bin/sh
set -e

# Only wait for postgres if all variables are set
if [ -n "$POSTGRES_HOST" ] && [ -n "$POSTGRES_PORT" ] && [ -n "$POSTGRES_USER" ]; then
  echo "Waiting for PostgreSQL to be ready..."
  until pg_isready -h $POSTGRES_HOST -p $POSTGRES_PORT -U $POSTGRES_USER; do
    echo "PostgreSQL not ready, retrying..."
    sleep 2
  done
else
  echo "Skipping PostgreSQL check - env vars not set"
fi

echo "Running migrations..."
python manage.py migrate --noinput

echo "Collecting static files..."
python manage.py collectstatic --noinput

if [ "$SERVICE" = "celery" ]; then
  celery -A NEXORAA worker --loglevel=info
elif [ "$SERVICE" = "celery-beat" ]; then
  celery -A NEXORAA beat --loglevel=info
elif [ "$SERVICE" = "server" ]; then
  if [ "$DJANGO_ENV" = "production" ]; then
    gunicorn NEXORAA.wsgi:application --bind 0.0.0.0:8000 --workers 2
  else
    python manage.py runserver 0.0.0.0:8000
  fi
else
  echo "Invalid SERVICE: $SERVICE"
  exit 1
fi