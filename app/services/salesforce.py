from simple_salesforce import Salesforce
from app.core.config import settings
import threading

# Use a thread-local storage to ensure the connection is unique per thread
local = threading.local()

def get_salesforce_connection():
    """
    Establishes and returns a thread-safe Salesforce connection using the
    Username-Password flow.
    It reads credentials from the environment settings.
    """
    if not hasattr(local, 'sf_connection'):
        print("Creating new Salesforce connection for this thread...")
        try:
            # This block now uses the username, password, and security token
            # for authentication.
            local.sf_connection = Salesforce(
                username=settings.SALESFORCE_USERNAME,
                password=settings.SALESFORCE_PASSWORD,
                security_token=settings.SALESFORCE_SECURITY_TOKEN,
                instance_url=settings.SALESFORCE_INSTANCE_URL
            )
            print("Salesforce connection successful.")
        except Exception as e:
            print(f"FATAL: Salesforce connection failed: {e}")
            local.sf_connection = None
    return local.sf_connection
