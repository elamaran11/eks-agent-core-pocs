"""
MCP Server exposing AgentCore Browser capabilities
"""
import os
import logging
from typing import Dict, Any
from fastmcp import FastMCP
from starlette.responses import JSONResponse
from contextlib import suppress

from bedrock_agentcore.tools.browser_client import BrowserClient
from browser_use import Agent as BrowserAgent
from browser_use.browser.session import BrowserSession
from browser_use.browser import BrowserProfile
from langchain_aws import ChatBedrockConverse

# Langfuse observability
from langfuse import Langfuse, observe

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("browser-mcp-server")

# Initialize MCP server
mcp = FastMCP("Browser MCP Server")

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
BROWSER_ID = os.environ.get("BROWSER_ID")
AWS_REGION = os.environ.get("AWS_REGION", "us-west-2")


@observe(name="browser_task_execution")
async def run_browser_task(browser_session, bedrock_chat, task: str) -> str:
    """Run a browser automation task"""
    agent = BrowserAgent(task=task, llm=bedrock_chat, browser=browser_session)
    result = await agent.run()
    
    if 'done' in result.last_action() and 'text' in result.last_action()['done']:
        return result.last_action()['done']['text']
    else:
        raise ValueError("No data returned from browser task")


async def initialize_browser_session():
    """Initialize Browser session with AgentCore"""
    client = BrowserClient(AWS_REGION)
    client.start(identifier=BROWSER_ID)
    
    ws_url, headers = client.generate_ws_headers()
    browser_profile = BrowserProfile(headers=headers, timeout=150000)
    browser_session = BrowserSession(cdp_url=ws_url, browser_profile=browser_profile, keep_alive=True)
    
    await browser_session.start()
    
    bedrock_chat = ChatBedrockConverse(
        model_id="us.anthropic.claude-3-7-sonnet-20250219-v1:0",
        region_name=AWS_REGION
    )
    
    return browser_session, bedrock_chat, client


@mcp.tool()
@observe(name="mcp_get_weather_data")
async def get_weather_data(city: str) -> Dict[str, Any]:
    """Get weather data for a city using browser automation.
    
    Args:
        city: The city name to get weather data for
        
    Returns:
        Dictionary with weather forecast data
    """
    if not BROWSER_ID:
        return {"status": "error", "content": [{"text": "BROWSER_ID not configured"}]}
    
    browser_session = None
    browser_client = None
    
    try:
        browser_session, bedrock_chat, browser_client = await initialize_browser_session()
        
        task = f"""Extract 8-Day Weather Forecast for {city} from weather.gov
        Steps:
        - Go to https://weather.gov
        - Search for "{city}" and click GO
        - Click "Printable Forecast" link
        - Extract date, high, low, conditions, wind, precip for each day
        - Return JSON array of daily forecasts
        """
        
        result = await run_browser_task(browser_session, bedrock_chat, task)
        
        if browser_client:
            browser_client.stop()

        return {"status": "success", "content": [{"text": result}]}
        
    except Exception as e:
        return {"status": "error", "content": [{"text": f"Error: {str(e)}"}]}
        
    finally:
        if browser_session:
            with suppress(Exception):
                await browser_session.close()


@mcp.tool()
@observe(name="mcp_browse_url")
async def browse_url(url: str, task: str) -> Dict[str, Any]:
    """Browse a URL and perform a task using browser automation.
    
    Args:
        url: The URL to navigate to
        task: The task to perform on the page
        
    Returns:
        Dictionary with task results
    """
    if not BROWSER_ID:
        return {"status": "error", "content": [{"text": "BROWSER_ID not configured"}]}
    
    browser_session = None
    browser_client = None
    
    try:
        browser_session, bedrock_chat, browser_client = await initialize_browser_session()
        
        full_task = f"""Navigate to {url} and perform the following task:
        {task}
        """
        
        result = await run_browser_task(browser_session, bedrock_chat, full_task)
        
        if browser_client:
            browser_client.stop()

        return {"status": "success", "content": [{"text": result}]}
        
    except Exception as e:
        return {"status": "error", "content": [{"text": f"Error: {str(e)}"}]}
        
    finally:
        if browser_session:
            with suppress(Exception):
                await browser_session.close()


if __name__ == "__main__":
    mcp.run(transport="sse", host="0.0.0.0", port=8080)
