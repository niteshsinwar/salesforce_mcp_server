"""Gemini AI orchestrator for processing user queries"""
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
    """Recursively converts protobuf objects to native Python types."""
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
        return getattr(obj, kind)
    if isinstance(obj, Mapping):
        return {key: _convert_proto_to_dict(value) for key, value in obj.items()}
    return obj

def _sanitize_schema(schema: dict):
    """Recursively sanitizes a JSON schema dictionary for Google AI library."""
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
    Acts as the Host, managing a multi-turn conversation with Gemini.
    """
    logger.info(f"Orchestrator received query: '{query}'")
    
    model = genai.GenerativeModel(model_name='gemini-2.0-flash-exp')
    history = [protos.Content(parts=[protos.Part(text=query)], role="user")]
    
    tool_failure_counts = defaultdict(int)
    max_iterations = 20
    
    for i in range(max_iterations):
        logger.info(f"--- Iteration {i+1}/{max_iterations} ---")
        
        # Prepare tools
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
        
        logger.info(f"Available tools: {tool_names}")
        
        try:
            response = model.generate_content(history, tools=current_tools)
            
            if not response.candidates or not response.candidates[0].content:
                logger.warning("Model returned no candidates")
                break
            
            response_content = response.candidates[0].content
            function_calls = [part.function_call for part in response_content.parts if part.function_call]
            
            if not function_calls:
                logger.info("No function calls - final response ready")
                break
            
            history.append(response_content)
            
            # Execute function calls
            function_response_parts = []
            for function_call in function_calls:
                tool_name = function_call.name
                raw_args = {key: value for key, value in function_call.args.items()}
                tool_args = _convert_proto_to_dict(raw_args)
                
                logger.info(f"Calling tool '{tool_name}' with args: {tool_args}")
                
                try:
                    if tool_name not in tool_registry:
                        raise ValueError(f"Tool '{tool_name}' not found")
                    
                    tool_function = tool_registry[tool_name]["function"]
                    tool_result = tool_function(**tool_args)
                    tool_result_str = str(tool_result)
                    
                    logger.info(f"Tool '{tool_name}' result: {tool_result_str[:500]}...")
                    
                    # Check for errors
                    is_error = "error" in tool_result_str.lower() or "failed" in tool_result_str.lower()
                    if is_error:
                        tool_failure_counts[tool_name] += 1
                        if tool_failure_counts[tool_name] > 2:
                            tool_result_str = f"Error: Tool '{tool_name}' failed multiple times. Try a different approach."
                    else:
                        tool_failure_counts[tool_name] = 0
                
                except Exception as e:
                    logger.error(f"Tool execution error: {e}")
                    tool_result_str = f"Error: Tool execution failed: {e}"
                
                function_response_parts.append(protos.Part(
                    function_response=protos.FunctionResponse(
                        name=tool_name, 
                        response={"result": tool_result_str}
                    )
                ))
            
            history.append(protos.Content(parts=function_response_parts, role="user"))
        
        except Exception as e:
            logger.error(f"Orchestrator error: {e}")
            return f"An error occurred: {e}"
    
    # Extract final response
    try:
        final_text_parts = [part.text for part in response.candidates[0].content.parts if part.text]
        final_text = "\n".join(final_text_parts)
        if not final_text:
            final_text = "Task completed successfully."
    except (IndexError, AttributeError, ValueError):
        final_text = "Task completed successfully."
    
    logger.info("Orchestration complete")
    return final_text
