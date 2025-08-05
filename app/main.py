import sys
import os
import uvicorn
from fastapi import FastAPI, Request, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.api import chat_endpoint
from app.mcp.server import mcp_server, tool_registry
import logging
from typing import Optional

# Load environment variables
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Import all MCP tools
from app.mcp.tools import *

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title=settings.PROJECT_NAME)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat_endpoint.router, prefix="/chat", tags=["Chat"])

@app.get("/")
def read_root():
    """Health check endpoint with mode detection."""
    mode = "local" if settings.is_local else "cloud"
    return {
        "message": f"Welcome to {settings.PROJECT_NAME} ({mode} mode)",
        "status": "ok",
        "mode": mode,
        "tools_available": len(tool_registry)
    }

@app.get("/health")
def health_check():
    """Detailed health check for monitoring."""
    return {
        "status": "healthy",
        "service": settings.PROJECT_NAME,
        "mode": "local" if settings.is_local else "cloud",
        "tools_count": len(tool_registry)
    }

# ✅ NEW: MCP HTTP Endpoint (This was missing!)
@app.post("/mcp")
async def mcp_endpoint(
    request: Request,
    mcp_api_key: Optional[str] = Header(None)
):
    """HTTP endpoint for MCP JSON-RPC protocol"""
    
    # Enhanced API key checking
    if settings.is_cloud:
        # Check multiple header variations (case-insensitive)
        headers = {k.lower(): v for k, v in request.headers.items()}
        api_key = (
            headers.get("mcp-api-key") or
            headers.get("x-api-key") or
            mcp_api_key
        )
        
        expected_key = settings.API_KEY
        if expected_key and (not api_key or api_key.strip() != expected_key.strip()):
            logger.warning(f"Unauthorized MCP access from {request.client.host}")
            raise HTTPException(status_code=401, detail="Invalid API key")
    
    try:
        body = await request.json()
        method = body.get("method")
        rpc_id = body.get("id")
        
        # Handle MCP protocol methods
        if method == "initialize":
            return {
                "jsonrpc": "2.0",
                "id": rpc_id,
                "result": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {"tools": {}},
                    "serverInfo": {
                        "name": settings.PROJECT_NAME,
                        "version": settings.VERSION
                    }
                }
            }
        
        elif method == "tools/list":
            tools = []
            for tool_name, tool_data in tool_registry.items():
                tools.append({
                    "name": tool_name,
                    "description": tool_data["description"],
                    "inputSchema": tool_data["schema"].model_json_schema()
                })
            
            return {
                "jsonrpc": "2.0",
                "id": rpc_id,
                "result": {"tools": tools}
            }
        
        elif method == "tools/call":
            tool_name = body["params"]["name"]
            arguments = body["params"].get("arguments", {})
            
            if tool_name not in tool_registry:
                return {
                    "jsonrpc": "2.0",
                    "id": rpc_id,
                    "error": {"code": -32601, "message": f"Tool '{tool_name}' not found"}
                }
            
            try:
                tool_function = tool_registry[tool_name]["function"]
                result = tool_function(**arguments)
                
                return {
                    "jsonrpc": "2.0",
                    "id": rpc_id,
                    "result": {"content": [{"type": "text", "text": str(result)}]}
                }
            except Exception as e:
                logger.error(f"Tool execution error: {e}")
                return {
                    "jsonrpc": "2.0", 
                    "id": rpc_id,
                    "error": {"code": -32603, "message": f"Tool error: {str(e)}"}
                }
        
        else:
            return {
                "jsonrpc": "2.0",
                "id": rpc_id,
                "error": {"code": -32601, "message": f"Method '{method}' not found"}
            }
    
    except Exception as e:
        logger.error(f"MCP endpoint error: {e}")
        return {
            "jsonrpc": "2.0",
            "id": body.get("id") if 'body' in locals() else None,
            "error": {"code": -32603, "message": str(e)}
        }


if __name__ == "__main__":
    if "--mcp-stdio" in sys.argv:
        logger.info("🚀 Starting MCP server in stdio mode (local)")
        mcp_server.run(transport='stdio')
    else:
        port = int(os.getenv("PORT", 8000))
        is_local = settings.is_local
        
        logger.info(f"🌐 Starting FastAPI server on 0.0.0.0:{port}")
        logger.info(f"📍 Mode: {'Local Development' if is_local else 'Cloud Production'}")
        logger.info(f"🔧 MCP HTTP endpoint: /mcp")
        logger.info(f"🛠️ Tools registered: {len(tool_registry)}")
        
        uvicorn.run(
            "app.main:app",
            host="0.0.0.0",
            port=port,
            reload=is_local,
            log_level="info"
        )
