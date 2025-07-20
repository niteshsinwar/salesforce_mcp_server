import google.generativeai as genai
from google.generativeai import protos
from app.core.config import settings
from app.mcp.server import tool_registry
import logging
import json
from collections import defaultdict
from typing import Any, Dict, List, Union
from collections.abc import Mapping
from google.protobuf.struct_pb2 import Value, Struct, ListValue

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

genai.configure(api_key=settings.GEMINI_API_KEY)

def _convert_proto_to_dict(obj: Any) -> Any:
    """
    Recursively and robustly converts protobuf Struct, ListValue, and Value 
    objects into native Python types (dicts, lists, primitives).
    """
    if isinstance(obj, Struct):
        return {key: _convert_proto_to_dict(value) for key, value in obj.items()}
    if isinstance(obj, ListValue):
        return [_convert_proto_to_dict(value) for value in obj]
    if isinstance(obj, Value):
        kind = obj.WhichOneof('kind')
        if kind == 'struct_value' or kind == 'list_value':
            return _convert_proto_to_dict(getattr(obj, kind))
        elif kind == 'null_value':
            return None
        # For primitives like 'number_value', 'string_value', 'bool_value'
        return getattr(obj, kind)
    
    # Handles the top-level MapComposite from the model's function call arguments
    if isinstance(obj, Mapping):
        return {key: _convert_proto_to_dict(value) for key, value in obj.items()}

    # Return primitives and other unhandled types as-is
    return obj

def _sanitize_schema(schema: dict):
    """
    Recursively sanitizes a JSON schema dictionary for the Google AI library.
    """
    keys_to_pop = []
    if isinstance(schema, dict):
        for key, value in schema.items():
            if key in ['title', 'default', 'additionalProperties']:
                keys_to_pop.append(key)
            if isinstance(value, dict):
                _sanitize_schema(value)
            elif isinstance(value, list):
                for item in value:
                    _sanitize_schema(item)
        
        for key in keys_to_pop:
            schema.pop(key, None)

        if 'anyOf' in schema:
             non_null_schema = next((item for item in schema['anyOf'] if item.get('type') != 'null'), None)
             if non_null_schema:
                 for k, v in non_null_schema.items():
                     if k not in schema:
                        schema[k] = v
             schema.pop('anyOf')

        if 'type' in schema and isinstance(schema.get('type'), str):
            schema['type'] = schema['type'].upper()

    elif isinstance(schema, list):
        for item in schema:
            _sanitize_schema(item)
            
    return schema

async def process_user_query(query: str) -> str:
    """
    Acts as the Host, managing a multi-turn conversation with Gemini to fulfill user requests.
    This version includes deep logging, enhanced self-correction, and proper protobuf conversion.
    """
    logger.info(f"Orchestrator received new query: '{query}'")
    
    model = genai.GenerativeModel(model_name='gemini-2.5-pro')
    history = [protos.Content(parts=[protos.Part(text=query)], role="user")]
    
    tool_failure_counts = defaultdict(int)
    
    max_iterations = 20
    for i in range(max_iterations):
        logger.info(f"--- Orchestrator Iteration {i+1}/{max_iterations} ---")
        
        schema_copy = json.loads(json.dumps([data["schema"].model_json_schema() for data in tool_registry.values()]))
        sanitized_schemas = [_sanitize_schema(s) for s in schema_copy]
        tool_names = list(tool_registry.keys())
        tool_descriptions = [data['description'] for data in tool_registry.values()]
        current_tools = [
            protos.Tool(function_declarations=[
                protos.FunctionDeclaration(
                    name=tool_names[i],
                    description=tool_descriptions[i],
                    parameters=sanitized_schemas[i]
                )
            ])
            for i in range(len(tool_names))
        ]
        logger.info(f"Available tools for this turn: {list(tool_registry.keys())}")
        
        try:
            response = model.generate_content(history, tools=current_tools)
            
            if not response.candidates or not response.candidates[0].content:
                logger.warning("Model returned no candidates. Ending conversation.")
                break
                
            response_content = response.candidates[0].content
            function_calls = [part.function_call for part in response_content.parts if part.function_call]
            
            if not function_calls:
                logger.info("No more function calls. Model is providing final response.")
                break
            
            history.append(response_content)
            
            logger.info("--- AI THOUGHT PROCESS ---")
            for fc in function_calls:
                logger.info(
                    f"Model wants to call tool: '{fc.name}' with raw arguments:\n"
                    f"{json.dumps(dict(fc.args), indent=2, default=str)}"
                )
            logger.info("--------------------------")

            function_response_parts = []
            for function_call in function_calls:
                tool_name = function_call.name
                
                raw_args = {key: value for key, value in function_call.args.items()}
                tool_args = _convert_proto_to_dict(raw_args)
                
                logger.info(f"Raw args before conversion: {raw_args}")
                logger.info(f"Converted args for tool '{tool_name}': {tool_args}")
                
                tool_result_str = ""
                try:
                    if tool_name not in tool_registry:
                        raise ValueError(f"Tool '{tool_name}' not found.")
                        
                    tool_function = tool_registry[tool_name]["function"]
                    tool_result = tool_function(**tool_args)
                    tool_result_str = str(tool_result)

                    logger.info(f"--- RAW TOOL OUTPUT ---\nOutput from '{tool_name}':\n{tool_result_str}\n-----------------------")
                    
                    is_error = "error" in tool_result_str.lower() or "failed" in tool_result_str.lower()
                    
                    if is_error:
                        tool_failure_counts[tool_name] += 1
                        logger.warning(f"Tool '{tool_name}' reported an error. Failure count: {tool_failure_counts[tool_name]}. Initiating self-correction.")

                        if tool_failure_counts[tool_name] > 2:
                            tool_result_str = (
                                f"Error: The tool '{tool_name}' has failed multiple times. "
                                f"Consider using a different approach or check the Salesforce API version. "
                                f"For SOQL queries, ensure you're using the correct endpoint format: "
                                f"'/services/data/v58.0/query' with params={{'q': ' lançamentoSELECT Id, Name FROM Account LIMIT 10'}}"
                            )
                        else:
                            tool_result_str = (
                                f"Error: Tool call failed: '{tool_result_str}'. "
                                f"Re-evaluate the parameters and try again. "
                                f"Check API version, endpoint format, and parameter structure. "
                                f"For SOQL queries, ensure the 'q' parameter contains the query string."
                            )
                    else:
                        tool_failure_counts[tool_name] = 0
                    
                except Exception as e:
                    logger.error(f"Critical tool execution error for '{tool_name}': {e}", exc_info=True)
                    tool_result_str = f"Critical Error: An unexpected exception occurred while running the tool: {e}. Check argument types and API endpoint format."

                function_response_parts.append(protos.Part(
                    function_response=protos.FunctionResponse(name=tool_name, response={"result": tool_result_str})
                ))

            history.append(protos.Content(parts=function_response_parts, role="user"))
            logger.info(f"Added {len(function_response_parts)} function responses to history for the next iteration.")
            
        except Exception as e:
            logger.critical(f"A critical error occurred in the orchestrator loop: {e}", exc_info=True)
            return f"An error occurred while processing your request: {e}"

    try:
        final_text_parts = [part.text for part in response.candidates[0].content.parts if part.text]
        final_text = "\n".join(final_text_parts)
        if not final_text:
             final_text = "I have completed the requested tasks."
    except (IndexError, AttributeError, ValueError):
        final_text = "I have completed the requested tasks."
        logger.warning("Could not extract final text from model response. Using a default message.")
        
    logger.info("--- Orchestration Complete ---")
    return final_text