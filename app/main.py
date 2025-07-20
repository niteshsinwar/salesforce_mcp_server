import sys
import uvicorn
from fastapi import FastAPI
from app.core.config import settings
from app.api import chat_endpoint
from app.mcp.server import mcp_server # Import the mcp_server instance

# This import is crucial. It triggers the code in `app/mcp/tools/__init__.py`
# which in turn loads all your plug-and-play MCP tools.
from app.mcp.tools import *

# --- FastAPI App Setup (for curl/web) ---
app = FastAPI(title=settings.PROJECT_NAME)

# Include the chat router. All requests to '/chat/' will be handled by it.
app.include_router(chat_endpoint.router, prefix="/chat", tags=["Chat"])

@app.get("/")
def read_root():
    """A simple health check endpoint."""
    return {"message": f"Welcome to the {settings.PROJECT_NAME}", "status": "ok"}


# --- Main execution block to choose the run mode ---
if __name__ == "__main__":
    # Check if a special command-line flag is provided
    if "--mcp-stdio" in sys.argv:
        # This mode is for Claude Desktop, which communicates over stdio
        print("--- [MCP] Starting in stdio mode ---")
        # The run() method blocks and handles stdio communication.
        # NOTE: In this mode, the server does NOT use the host/orchestrator logic.
        # It expects the client (Claude Desktop) to act as the host.
        mcp_server.run(transport='stdio')
    else:
        # This is the default mode for running as a web server
        print("--- [HTTP] Starting FastAPI web server ---")
        uvicorn.run(app, host="0.0.0.0", port=8000)
