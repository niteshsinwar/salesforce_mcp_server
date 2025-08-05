import sys
import os
import uvicorn
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.api import chat_endpoint
from app.mcp.server import mcp_server
import logging

# Load environment variables for local development
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv not available in production

# This import is crucial - loads all MCP tools
from app.mcp.tools import *

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- FastAPI App Setup (for web/HTTP mode) ---
app = FastAPI(title=settings.PROJECT_NAME)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include your existing chat router
app.include_router(chat_endpoint.router, prefix="/chat", tags=["Chat"])

@app.get("/")
def read_root():
    """Health check endpoint with mode detection."""
    mode = "local" if os.getenv("RENDER") is None else "cloud"
    return {
        "message": f"Welcome to {settings.PROJECT_NAME} ({mode} mode)",
        "status": "ok",
        "mode": mode
    }

@app.get("/health")
def health_check():
    """Detailed health check for monitoring."""
    return {
        "status": "healthy",
        "service": settings.PROJECT_NAME,
        "mode": "local" if os.getenv("RENDER") is None else "cloud"
    }

# API Key middleware for cloud deployment security
@app.middleware("http")
async def api_key_middleware(request: Request, call_next):
    """Protect MCP routes with API key in cloud mode."""
    # Only enforce API key in cloud mode and for MCP routes
    if os.getenv("RENDER") and request.url.path.startswith("/mcp"):
        api_key = request.headers.get("mcp-api-key")
        expected_key = os.getenv("API_KEY")
        if expected_key and (api_key != expected_key):
            logger.warning(f"Unauthorized MCP access attempt")
            raise HTTPException(status_code=401, detail="Invalid API key")
    
    response = await call_next(request)
    return response

# --- Main execution block to choose the run mode ---
if __name__ == "__main__":
    if "--mcp-stdio" in sys.argv:
        # MCP stdio mode for Claude Desktop local connection
        logger.info("🚀 Starting MCP server in stdio mode (local)")
        mcp_server.run(transport='stdio')
    else:
        # HTTP mode for both local testing and cloud deployment
        port = int(os.getenv("PORT", 8000))
        is_local = os.getenv("RENDER") is None
        
        logger.info(f"🌐 Starting FastAPI server on 0.0.0.0:{port}")
        logger.info(f"📍 Mode: {'Local Development' if is_local else 'Cloud Production'}")
        
        uvicorn.run(
            "app.main:app",
            host="0.0.0.0", 
            port=port,
            reload=is_local,  # Auto-reload only in local mode
            log_level="info"
        )
