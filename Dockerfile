FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Crée le dossier assets si absent (les images sont montées en volume)
RUN mkdir -p static/assets

EXPOSE 8000

# Initialise la DB au premier démarrage, puis lance gunicorn
CMD ["sh", "-c", "python init_db.py && gunicorn --bind 0.0.0.0:8000 --workers 2 app:app"]
