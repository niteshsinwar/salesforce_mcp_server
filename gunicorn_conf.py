import multiprocessing
import os
import platform

# Port configuration
port = os.getenv("PORT", "8000")
bind = f"0.0.0.0:{port}"

# Worker configuration
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

# Platform-specific worker temp directory
if platform.system() == "Linux":
    # Use shared memory on Linux (Render, Docker, etc.)
    worker_tmp_dir = "/dev/shm"
    preload_app = True
else:
    # Use default temp dir on macOS/Windows
    worker_tmp_dir = None  # Uses system default
    preload_app = False    # Safer for development
