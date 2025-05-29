from celery import Celery
from dotenv import load_dotenv
load_dotenv()
import os

# It's better to read from rxconfig if possible, but for worker context,
# environment variables are robust.
REDIS_URL_FROM_ENV = os.getenv("REDIS_", "redis://redis:6379/0")
print(f"Using Redis URL: {REDIS_URL_FROM_ENV}")

celery_app = Celery(
    "worker", # Naming the celery application
    broker=REDIS_URL_FROM_ENV,
    backend=REDIS_URL_FROM_ENV,
    include=['app.tasks']  # We will add task modules here later
)

# Optional: Configuration settings
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
)
