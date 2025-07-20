import logging
import inspect
import requests
import ast
from typing import Union
import json
import re
from typing import Optional, Dict, Any, List
from simple_salesforce.exceptions import (
    SalesforceResourceNotFound,
    SalesforceMalformedRequest,
    SalesforceAuthenticationFailed,
    SalesforceError
)
import pandas as pd
import ast
from app.mcp.server import register_tool, add_tool_to_registry, tool_registry
from app.services.salesforce import get_salesforce_connection
sf = get_salesforce_connection()
logger = logging.getLogger(__name__)

# --- Level 1: The Go-To Tools for Standard Operations ---

@register_tool
def execute_soql_query(query: str) -> str:
    """
    Executes a Salesforce Object Query Language (SOQL) query to retrieve data. This is the most reliable and preferred tool for all read-only data retrieval tasks.

    **WHEN TO USE:**
    - Use this for any task that involves reading or fetching data from Salesforce.
    - It is the HIGH-PRIORITY tool for querying because it is safe, efficient, and automatically handles fetching all pages of results.

    **GUIDANCE:**
    - To avoid retrieving too much data, always include a `LIMIT` clause in your query unless you specifically need all records.
    - Double-check the API names for both the object (e.g., 'Account') and its fields (e.g., 'AnnualRevenue'). Invalid names are a common source of errors.

    Args:
        query: The complete, valid SOQL query string to execute.
               Example: "SELECT Id, Name, AnnualRevenue FROM Account WHERE Industry = 'Technology' ORDER BY LastModifiedDate DESC LIMIT 10"

    Returns:
        A JSON string of the query results, a success message if no records are found, or a formatted error message.
    """
    sf = get_salesforce_connection()
    if not isinstance(sf, object):
        return f"❌ Error: Could not establish connection to Salesforce. Details: {sf}"

    logger.info(f"Executing SOQL query: {query}")
    try:
        result = sf.query_all(query)
        records = result.get('records', [])
        
        if not records:
            return "✅ Query executed successfully: No records found."
        
        for r in records:
            r.pop('attributes', None)

        return json.dumps(records, indent=2, default=str)
    except Exception as e:
        error_message = f"❌ SOQL Query Error: {e}"
        logger.error(error_message)
        if "MALFORMED_QUERY" in str(e):
            error_message += "\nGUIDANCE: The SOQL query syntax is incorrect. Please check your SELECT statement, object/field names, and WHERE clause."
        elif "INVALID_FIELD" in str(e):
            error_message += "\nGUIDANCE: One or more fields in your query are invalid. Verify the API names of the fields for the specified object."
        return error_message

@register_tool
def execute_universal_api_request(
    method: str,
    sub_endpoint: str,
    body: Optional[Union[Dict[str, Any], str]] = None,
    params: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str, str]] = None,
    api_type: str = "rest",
    api_version: str = "v59.0",
    raw_response: bool = False,
    timeout: int = 30
) -> str:
    """
    Enhanced Universal Salesforce API executor supporting ALL Salesforce APIs with intelligent routing,
    endpoint validation, and comprehensive error handling.
    
    **SUPPORTED API TYPES & COMMON ENDPOINTS:**
    
    🔹 'rest' (DEFAULT): Standard Salesforce REST API
       - CRUD operations: sobjects/Account, sobjects/Contact/003xx0000004TmiAAE
       - Bulk operations: composite/tree/Account, composite/batch, composite/sobjects
       - Describe: sobjects/Account/describe, sobjects
       - Queries: query (but prefer execute_soql_query for SOQL)
       
    🔹 'tooling': Development & metadata operations
       - Apex queries: query?q=SELECT Id FROM ApexClass
       - Debug logs: sobjects/ApexLog
       - Metadata: sobjects/CustomObject
       
    Args:
        method: HTTP method ('GET', 'POST', 'PATCH', 'DELETE', 'PUT')
        sub_endpoint: API path after base URL (e.g., 'limits', 'sobjects/Account', 'composite/sobjects')
        body: Request payload. Can be dict, JSON string, or None
        params: URL query parameters for GET requests
        headers: Additional HTTP headers
        api_type: API type for routing ('rest', 'tooling'). Most endpoints use 'rest'.
        api_version: Salesforce API version (default: v59.0)
        raw_response: Return raw response without JSON formatting
        timeout: Request timeout in seconds (default: 30)
        
    Returns:
        Formatted API response with success/error indicators and actionable guidance
    """
    
    # Input validation
    if not method or not sub_endpoint:
        return "❌ Error: 'method' and 'sub_endpoint' are required parameters"
    
    sf = get_salesforce_connection()
    if not isinstance(sf, object):
        return f"❌ Connection error: {sf}"

    # Parse string body to dict if needed
    if isinstance(body, str) and body.strip():
        logger.info("Body provided as string, attempting JSON parsing")
        try:
            # Clean common prefixes from tool outputs
            clean_body = body.strip()
            if clean_body.startswith('✅'):
                clean_body = clean_body[1:].strip()
            
            body = json.loads(clean_body)
            logger.info("Successfully parsed string body to JSON")
        except json.JSONDecodeError as e:
            return f"❌ JSON Parse Error: Body string is not valid JSON.\nError: {e}\nBody content: {body[:200]}..."
    
    # Normalize inputs
    method = method.upper()
    api_type = api_type.lower()
    sub_endpoint = sub_endpoint.strip('/')
    
    # Define API base paths and validate api_type
    api_base_paths = {
        'rest': f"services/data/{api_version}",
        'tooling': f"services/data/{api_version}/tooling",
    }
    
    if api_type not in api_base_paths:
        return f"❌ Invalid api_type '{api_type}'. Valid options: {', '.join(api_base_paths.keys())}"
    
    # Build full endpoint
    full_endpoint = f"{api_base_paths[api_type]}/{sub_endpoint}"
    
    # Set appropriate headers
    default_headers = {
        'Content-Type': 'application/json',
        'Accept': 'application/json'
    }
    if headers:
        default_headers.update(headers)
    
    # Log request details
    logger.info(f"🔄 {api_type.upper()} API Request: {method} {full_endpoint}")
    if body:
        logger.info(f"📤 Request body size: {len(json.dumps(body)) if isinstance(body, dict) else len(str(body))} characters")
    if params:
        logger.info(f"📋 Query params: {params}")
    
    try:
        # Make the API request
        response = sf.restful(
            full_endpoint, 
            method=method,
            json=body,
            params=params,
            headers=default_headers,
            timeout=timeout
        )
        
        if raw_response:
            return str(response)
        
        result_str = json.dumps(response, indent=2, default=str)
        return f"✅ {api_type.upper()} API Success:\n{result_str}"
        
    except (SalesforceError, SalesforceMalformedRequest) as e:
        error_details = e.content if hasattr(e, 'content') else str(e)
        status_code = getattr(e, 'status', 'Unknown')
        
        guidance_map = {
            400: "Bad Request - Check payload structure and required fields.",
            404: "Not Found - Verify the endpoint URL is correct and the resource exists.",
            403: "Forbidden - Check permissions for the object or fields.",
        }
        guidance = guidance_map.get(status_code, "An unknown Salesforce API error occurred.")
        
        error_msg = (f"❌ {api_type.upper()} API Error ({status_code}): {error_details}\n"
                     f"📍 Endpoint: {full_endpoint}\n"
                     f"💡 Guidance: {guidance}")
        
        return error_msg
        
    except Exception as e:
        return f"❌ Unexpected Tool Error: {str(e)}\n📍 Context: {method} {full_endpoint}"



@register_tool
def create_python_tool_for_salesforce(function_code: str) -> str:
    """
    **POWERFUL META-TOOL:** Dynamically writes, defines, and registers a new Python function as a tool to perform complex, multi-step, or custom tasks.

    **SECURITY WARNING:** This tool executes generated Python code. The code must be safe, efficient, and strictly adhere to the rules below.

    **WHEN TO USE:**
    - For **multi-step processes**, such as querying for data, processing it, and then updating other records.
    - For **bulk operations**, like updating or deleting thousands of records based on specific criteria.
    - For tasks requiring **custom logic** or data manipulation that cannot be done with a single API call.
    - For tasks that benefit from using the **Pandas library** for data transformation.

    **RULES FOR CODE GENERATION:**
    1.  **Function Signature:** The code MUST define a single Python function with a unique name, full type hints for all arguments (e.g., `arg_name: str`), and a `-> str` return annotation.
    2.  **Error Handling:** The entire logic inside the function MUST be wrapped in a single `try...except Exception as e:` block to catch all potential errors.
    3.  **Return Value:** The function MUST return a descriptive string. This string **MUST** be prefixed with "✅ " for success or "❌ " for failure.
    4.  **Salesforce Connection:** The first line inside the `try` block MUST be `sf = get_salesforce_connection()` followed by a check to ensure the connection is valid.

    **AVAILABLE LIBRARIES:**
    The following modules are pre-imported and available in the function's scope. **DO NOT** write `import` statements for these in your generated code.
    - `json`: For working with JSON data.
    - `pandas as pd`: For powerful data manipulation.
    - `get_salesforce_connection`: Function to get the Salesforce connection object.
    - `date`, `datetime`, `timedelta`: For all date and time operations.

    **--- GENERIC USAGE EXAMPLE ---**
    This example shows a flexible tool that finds recently modified records for any given Salesforce object.
    '''python
    def find_recent_records(object_name: str, days_ago: int) -> str:
        \"\"\"
        Finds records of a given SObject type modified in the last N days.

        Args:
            object_name: The API name of the Salesforce object (e.g., 'Account', 'Lead').
            days_ago: The number of days to look back for modifications.

        Returns:
            A JSON string of the records found, or an error message.
        \"\"\"
        try:
            sf = get_salesforce_connection()
            if not isinstance(sf, object):
                return f"❌ Error: Could not connect to Salesforce: {sf}"

            # 'date' and 'timedelta' are pre-imported and ready to use.
            target_date = (date.today() - timedelta(days=days_ago)).isoformat()
            
            # This demonstrates dynamically building a query from arguments.
            query = f"SELECT Id, Name, LastModifiedDate FROM {object_name} WHERE LastModifiedDate >= {target_date} ORDER BY LastModifiedDate DESC"
            
            results = sf.query_all(query)
            records = results.get('records', [])
            
            if not records:
                return "✅ Query successful: No records found matching the criteria."

            for r in records:
                r.pop('attributes', None)

            # 'json' is pre-imported and ready to use.
            return f"✅ {json.dumps(records, indent=2)}"
        except Exception as e:
            return f"❌ An error occurred while querying {object_name} records: {e}"
    '''
    """
    # The implementation of the function remains the same as the corrected version from the previous turn.
    logger.warning("--- [SECURITY WARNING] Executing dynamic code from create_python_tool_for_salesforce ---")
    
    execution_globals = {
        "__builtins__": __builtins__,
        "requests": requests,
        "json": json,
        "logging": logging,
        "get_salesforce_connection": get_salesforce_connection,
        "pd": pd,
        "date": __import__('datetime').date,
        "datetime": __import__('datetime').datetime,
        "timedelta": __import__('datetime').timedelta,
    }
    local_scope = {}
    
    try:
        exec(function_code, execution_globals, local_scope)
        new_func_name = next((key for key, val in local_scope.items() if inspect.isfunction(val)), None)
        
        if not new_func_name:
            raise ValueError("No function was defined in the provided code string.")
        
        new_func = local_scope[new_func_name]
        add_tool_to_registry(new_func)
        
        if new_func_name not in tool_registry:
            raise ValueError(f"Tool '{new_func_name}' was not successfully registered in tool_registry.")
        
        success_message = f"✅ Successfully defined and registered new tool: '{new_func_name}'. You may now call this tool to complete the task."
        logger.info(success_message)
        return success_message

    except SyntaxError as se:
        error_message = (
            f"❌ Syntax Error in generated code at line {se.lineno}: {se.msg}\n"
            f"Code snippet: {se.text.strip() if se.text else 'N/A'}\n"
            f"GUIDANCE: Check the syntax of your Python code. Ensure proper indentation and valid Python syntax."
        )
        logger.error(error_message, exc_info=True)
        return error_message
    except Exception as e:
        error_message = (
            f"❌ Failed to define the new tool. Error: {e}\n"
            f"Full code:\n{function_code}\n"
            "GUIDANCE: Ensure the code defines a single function with a docstring, uses allowed imports (json, get_salesforce_connection), "
            "starts with a Salesforce connection check, and includes a try/except block."
        )
        logger.error(error_message, exc_info=True)
        return error_message