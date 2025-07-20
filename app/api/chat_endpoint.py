from fastapi import APIRouter, Depends, Body
from app.core.security import get_api_key
from app.host.orchestrator import process_user_query
from pydantic import BaseModel

router = APIRouter()

class ChatRequest(BaseModel):
    query: str
    salesforce_user_id: str

@router.post("/")
async def chat_endpoint(
    request: ChatRequest,
    api_key: str = Depends(get_api_key)
):
    """
    Receives a user query from Salesforce, processes it via the orchestrator,
    and returns a final response. This endpoint is protected by an API key.
    """
    response_text = await process_user_query(request.query)
    return {"response": response_text}
