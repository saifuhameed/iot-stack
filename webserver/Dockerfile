FROM python:3.13-slim
WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt gunicorn

# Copy app code
COPY . .

# Expose port 80 inside container
EXPOSE 80


# Run Gunicorn directly (no authbind needed)
CMD ["gunicorn", "--workers", "2", "--bind", "0.0.0.0:80", "main:app"]
