import inspect
import pydantic
from mcp.server.fastmcp import FastMCP

# --- Self-reliant Helper Functions (to replace the problematic import) ---

def parse_docstring(func):
    """A simple parser for a standard Python docstring."""
    docstring = inspect.getdoc(func)
    if not docstring:
        return "No description available.", {}
    
    lines = docstring.strip().split('\n')
    description = lines[0].strip()
    
    arg_descriptions = {}
    args_section = False
    for line in lines[1:]:
        line = line.strip()
        if line.lower() in ('args:', 'parameters:'):
            args_section = True
            continue
        if args_section and ':' in line:
            arg_name, arg_desc = line.split(':', 1)
            arg_descriptions[arg_name.strip()] = arg_desc.strip()
            
    return description, arg_descriptions

def create_model_from_func(func, arg_descriptions):
    """Creates a Pydantic model from a function's signature and descriptions."""
    fields = {}
    for param in inspect.signature(func).parameters.values():
        field_info = {
            "description": arg_descriptions.get(param.name, ""),
        }
        if param.default is not inspect.Parameter.empty:
            field_info["default"] = param.default
        
        fields[param.name] = (param.annotation, pydantic.Field(**field_info))
        
    return pydantic.create_model(f"{func.__name__}Schema", **fields)

# --- MCP Server and Tool Registry Setup ---

mcp_server = FastMCP(name="salesforce-production-server", version="2.0.0")
tool_registry = {}

def add_tool_to_registry(func):
    """
    Parses a function, generates its schema, and adds it to the global tool_registry.
    This is the core logic used by both static and dynamic tool registration.
    """
    tool_name = func.__name__

    # 1. Use our self-reliant functions to get the tool's metadata.
    description, arg_descriptions = parse_docstring(func)
    schema = create_model_from_func(func, arg_descriptions)

    # 2. Add this predictable information to our own public registry.
    tool_registry[tool_name] = {
        "name": tool_name,
        "description": description,
        "schema": schema,
        "function": func
    }
    
    # 3. Finally, register the original function with the underlying MCP library.
    # This is important for other potential integrations.
    mcp_server.tool()(func)
    
    print(f"  -> [MCP] Registered '{tool_name}'")


def register_tool(func):
    """
    A decorator that registers a function as a tool using the core logic.
    """
    add_tool_to_registry(func)
    return func
