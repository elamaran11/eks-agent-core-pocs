"""
MCP Server exposing Code Interpreter as an MCP Tool
Only exposes execute_code - other tools remain local to the agent
"""
import os
import json
import logging
from typing import Dict, Any
from fastmcp import FastMCP
from starlette.responses import JSONResponse

from bedrock_agentcore.tools.code_interpreter_client import CodeInterpreter

# Langfuse observability
from langfuse import Langfuse, observe

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("code-mcp-server")

# Initialize MCP server
mcp = FastMCP("Execute Code MCP Server")

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
CODE_INTERPRETER_ID = os.environ.get("CODE_INTERPRETER_ID")
AWS_REGION = os.environ.get("AWS_REGION", "us-west-2")


@mcp.tool()
@observe(name="mcp_execute_code")
def execute_code(python_code: str) -> Dict[str, Any]:
    """Execute Python code using AgentCore Code Interpreter.
    
    Args:
        python_code: The Python code to execute
        
    Returns:
        Dictionary with status and execution results
    """
    try:
        if not CODE_INTERPRETER_ID:
            return {"status": "error", "content": [{"text": "CODE_INTERPRETER_ID not configured"}]}
            
        code_client = CodeInterpreter(AWS_REGION)
        code_client.start(identifier=CODE_INTERPRETER_ID)

        response = code_client.invoke("executeCode", {
            "code": python_code,
            "language": "python",
            "clearContext": True
        })

        code_execute_result = None
        for event in response["stream"]:
            code_execute_result = json.dumps(event["result"])
        
        if code_execute_result:
            analysis_results = json.loads(code_execute_result)
            return {"status": "success", "content": [{"text": str(analysis_results)}]}
        else:
            return {"status": "error", "content": [{"text": "No result returned from code interpreter"}]}

    except Exception as e:
        return {"status": "error", "content": [{"text": f"Error: {str(e)}"}]}


if __name__ == "__main__":
    # Run with SSE transport for agentgateway compatibility
    mcp.run(transport="sse", host="0.0.0.0", port=8080)
