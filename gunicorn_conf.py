import multiprocessing
import os

# Render uses PORT environment variable (default 10000)
port = os.getenv("PORT", "10000")
bind = f"0.0.0.0:{port}"

# Optimized worker configuration
workers = min(multiprocessing.cpu_count() * 2 + 1, 4)
worker_class = "uvicorn.workers.UvicornWorker"

# Logging
loglevel = "info"
accesslog = "-"
errorlog = "-"

# Performance settings
timeout = 120
keepalive = 5
max_requests = 1000
max_requests_jitter = 100

# Memory optimization
preload_app = True
worker_tmp_dir = "/dev/shm"
