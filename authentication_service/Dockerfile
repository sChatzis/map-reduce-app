FROM python:3.11-slim AS builder

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Set the working directory
WORKDIR /app

# Copy requirements file and install dependencies
COPY ./requirements.txt /app/
RUN pip install --no-cache-dir -r /app/requirements.txt

# Final Image
FROM python:3.11-slim

WORKDIR /app

# Copy installed packages from the builder stage
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages

# Copy the application code
COPY ./app /app/app
# Copy the .env file (if you want to run it completely inside docker)
# Note: For production, we usually pass environment variables directly,
# but copying the .env file is simplest for development.
#COPY ./.env /app/.env

# Expose the port (FastAPI default is 8000)
EXPOSE 8000

# Run the application using uvicorn
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]