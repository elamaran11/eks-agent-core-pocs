"""
MCP Server exposing AgentCore Memory capabilities
"""
import os
import logging
from typing import Dict, Any
from fastmcp import FastMCP
from starlette.responses import JSONResponse

from bedrock_agentcore.memory import MemoryClient

# Langfuse observability
from langfuse import Langfuse, observe

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("memory-mcp-server")

# Initialize MCP server
mcp = FastMCP("Memory MCP Server")

# Langfuse configuration
LANGFUSE_PUBLIC_KEY = os.environ.get('LANGFUSE_PUBLIC_KEY')
LANGFUSE_SECRET_KEY = os.environ.get('LANGFUSE_SECRET_KEY')
LANGFUSE_HOST = os.environ.get('LANGFUSE_HOST', 'http://langfuse-web.langfuse.svc.cluster.local:3000')

langfuse_client = None
if LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY:
    langfuse_client = Langfuse(
        public_key=LANGFUSE_PUBLIC_KEY,
        secret_key=LANGFUSE_SECRET_KEY,
        host=LANGFUSE_HOST
    )
    logger.info(f"Langfuse observability enabled ({LANGFUSE_HOST})")
else:
    logger.warning("Langfuse not configured")

# Health check endpoint
@mcp.custom_route("/health", methods=["GET"])
async def health_check(request):
    return JSONResponse({"status": "healthy"})

# Get capability IDs from environment
MEMORY_ID = os.environ.get("MEMORY_ID")
AWS_REGION = os.environ.get("AWS_REGION", "us-west-2")


@mcp.tool()
@observe(name="mcp_store_user_preferences")
def store_user_preferences(preferences: str) -> Dict[str, Any]:
    """Store user activity preferences in memory.
    
    Args:
        preferences: The user preferences to store
        
    Returns:
        Dictionary with status of the operation
    """
    if not MEMORY_ID:
        return {"status": "success", "content": [{"text": "Memory not configured. Preferences not stored."}]}
    
    try:
        client = MemoryClient(region_name=AWS_REGION)
        client.save_turn(
            memory_id=MEMORY_ID,
            actor_id="user123",
            session_id="session456",
            user_input=f"My preferences: {preferences}",
            agent_response="Preferences saved"
        )
        return {"status": "success", "content": [{"text": f"Preferences stored: {preferences}"}]}
    except Exception as e:
        return {"status": "error", "content": [{"text": f"Error storing preferences: {str(e)}"}]}


@mcp.tool()
@observe(name="mcp_get_activity_preferences")
def get_activity_preferences() -> Dict[str, Any]:
    """Get user activity preferences from memory.
    
    Returns:
        Dictionary with user preferences
    """
    if not MEMORY_ID:
        return {"status": "success", "content": [{"text": "Memory not configured. Default: outdoor activities, hiking, beaches, museums."}]}
    
    try:
        client = MemoryClient(region_name=AWS_REGION)
        response = client.retrieve_memories(
            memory_id=MEMORY_ID,
            query="What are the user's activity preferences and interests?",
            max_results=5
        )
        
        if response and len(response) > 0:
            preferences = "\n".join([str(item) for item in response])
            return {"status": "success", "content": [{"text": f"User preferences: {preferences}"}]}
        else:
            return {"status": "success", "content": [{"text": "No preferences stored. Default: outdoor activities, hiking, beaches, museums."}]}
    except Exception as e:
        return {"status": "error", "content": [{"text": f"Error retrieving preferences: {str(e)}"}]}


@mcp.tool()
@observe(name="mcp_store_activity_plan")
def store_activity_plan(city: str, plan: str) -> Dict[str, Any]:
    """Store the activity plan in memory for future reference.
    
    Args:
        city: The city the plan is for
        plan: The activity plan to store
        
    Returns:
        Dictionary with status of the operation
    """
    if not MEMORY_ID:
        return {"status": "success", "content": [{"text": "Memory not configured. Plan not stored."}]}
    
    try:
        client = MemoryClient(region_name=AWS_REGION)
        client.save_turn(
            memory_id=MEMORY_ID,
            actor_id="user123",
            session_id="session456",
            user_input=f"Plan for {city}",
            agent_response=plan
        )
        return {"status": "success", "content": [{"text": f"Activity plan stored in memory for {city}"}]}
    except Exception as e:
        return {"status": "error", "content": [{"text": f"Error storing plan: {str(e)}"}]}


@mcp.tool()
@observe(name="mcp_store_memory")
def store_memory(key: str, value: str) -> Dict[str, Any]:
    """Store a key-value pair in memory.
    
    Args:
        key: The key/topic for the memory
        value: The value/content to store
        
    Returns:
        Dictionary with status of the operation
    """
    if not MEMORY_ID:
        return {"status": "success", "content": [{"text": "Memory not configured."}]}
    
    try:
        client = MemoryClient(region_name=AWS_REGION)
        client.save_turn(
            memory_id=MEMORY_ID,
            actor_id="user123",
            session_id="session456",
            user_input=key,
            agent_response=value
        )
        return {"status": "success", "content": [{"text": f"Stored: {key}"}]}
    except Exception as e:
        return {"status": "error", "content": [{"text": f"Error: {str(e)}"}]}


@mcp.tool()
@observe(name="mcp_retrieve_memory")
def retrieve_memory(query: str) -> Dict[str, Any]:
    """Retrieve memories matching a query.
    
    Args:
        query: The search query for memories
        
    Returns:
        Dictionary with matching memories
    """
    if not MEMORY_ID:
        return {"status": "success", "content": [{"text": "Memory not configured."}]}
    
    try:
        client = MemoryClient(region_name=AWS_REGION)
        response = client.retrieve_memories(
            memory_id=MEMORY_ID,
            query=query,
            max_results=5
        )
        
        if response and len(response) > 0:
            memories = "\n".join([str(item) for item in response])
            return {"status": "success", "content": [{"text": memories}]}
        else:
            return {"status": "success", "content": [{"text": "No matching memories found."}]}
    except Exception as e:
        return {"status": "error", "content": [{"text": f"Error: {str(e)}"}]}


if __name__ == "__main__":
    mcp.run(transport="sse", host="0.0.0.0", port=8080)
