from app.core.config import settings
from langchain_google_genai import ChatGoogleGenerativeAI

def get_crewai_llm():
    """
    Returns a configured instance of the ChatGoogleGenerativeAI LLM for CrewAI.
    """
    # This is the correct way to instantiate the Gemini model for use with CrewAI
    llm = ChatGoogleGenerativeAI(
        model="gemini-2.5-pro",
        verbose=True,
        temperature=0.5,
        google_api_key=settings.GEMINI_API_KEY
    )
    return llm
