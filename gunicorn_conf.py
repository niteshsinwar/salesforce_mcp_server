import multiprocessing
import os

# Render provides PORT environment variable
port = os.getenv("PORT", "8000")
bind = f"0.0.0.0:{port}"

# Worker configuration optimized for Render
workers = min(multiprocessing.cpu_count() * 2 + 1, 4)  # Max 4 workers
worker_class = "uvicorn.workers.UvicornWorker"

# Logging
loglevel = "info"
accesslog = "-"
errorlog = "-"

# Performance settings for cloud deployment
timeout = 120
keepalive = 5
max_requests = 1000
max_requests_jitter = 100

# Memory management
preload_app = True
worker_tmp_dir = "/dev/shm"  # Use shared memory for better performance
