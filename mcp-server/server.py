"""
MCP Server exposing Agent Core capabilities as MCP Tools
"""
import os
import json
from typing import Dict, Any
from fastapi import FastAPI
from pydantic import BaseModel
from contextlib import suppress

from bedrock_agentcore.tools.browser_client import BrowserClient
from browser_use import Agent as BrowserAgent
from browser_use.browser.session import BrowserSession
from browser_use.browser import BrowserProfile
from langchain_aws import ChatBedrockConverse
from bedrock_agentcore.tools.code_interpreter_client import CodeInterpreter
from bedrock_agentcore.memory import MemoryClient

app = FastAPI(title="Agent Core Tools")

# Get capability IDs from environment
MEMORY_ID = os.environ.get("MEMORY_ID")
BROWSER_ID = os.environ.get("BROWSER_ID")
CODE_INTERPRETER_ID = os.environ.get("CODE_INTERPRETER_ID")
AWS_REGION = os.environ.get("AWS_REGION", "us-west-2")


class WeatherRequest(BaseModel):
    city: str

class CodeRequest(BaseModel):
    weather_data: str

class ExecuteRequest(BaseModel):
    python_code: str

class PreferencesRequest(BaseModel):
    preferences: str

class PlanRequest(BaseModel):
    city: str
    plan: str


async def run_browser_task(browser_session, bedrock_chat, task: str) -> str:
    agent = BrowserAgent(task=task, llm=bedrock_chat, browser=browser_session)
    result = await agent.run()
    
    if 'done' in result.last_action() and 'text' in result.last_action()['done']:
        return result.last_action()['done']['text']
    else:
        raise ValueError("NO Data")


async def initialize_browser_session():
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


@app.post("/tools/get_weather_data")
async def get_weather_data(req: WeatherRequest):
    browser_session = None
    try:
        browser_session, bedrock_chat, browser_client = await initialize_browser_session()
        
        task = f"""Extract 8-Day Weather Forecast for {req.city} from weather.gov
        Steps:
        - Go to https://weather.gov
        - Search for "{req.city}" and click GO
        - Click "Printable Forecast" link
        - Extract date, high, low, conditions, wind, precip for each day
        - Return JSON array of daily forecasts
        """
        
        result = await run_browser_task(browser_session, bedrock_chat, task)
        
        if browser_client:
            browser_client.stop()

        return {"success": True, "result": result}
        
    except Exception as e:
        return {"success": False, "error": str(e)}
        
    finally:
        if browser_session:
            with suppress(Exception):
                await browser_session.close()


@app.post("/tools/generate_analysis_code")
async def generate_analysis_code(req: CodeRequest):
    try:
        llm = ChatBedrockConverse(
            model_id="us.anthropic.claude-3-7-sonnet-20250219-v1:0",
            region_name=AWS_REGION
        )
        
        query = f"""Create Python code to classify weather days as GOOD/OK/POOR:
        Rules: GOOD: 65-80°F clear, OK: 55-85°F partly cloudy, POOR: <55°F or >85°F
        Weather data: {req.weather_data}
        Return code that outputs list of tuples: [('2025-09-16', 'GOOD'), ...]"""
        
        result = llm.invoke(query)
        python_code = result.content
        
        import re
        pattern = r'```(?:json|python)\n(.*?)\n```'
        match = re.search(pattern, python_code, re.DOTALL)
        python_code = match.group(1).strip() if match else python_code
        
        return {"success": True, "result": python_code}
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.post("/tools/execute_code")
async def execute_code(req: ExecuteRequest):
    try:
        code_client = CodeInterpreter(AWS_REGION)
        code_client.start(identifier=CODE_INTERPRETER_ID)

        response = code_client.invoke("executeCode", {
            "code": req.python_code,
            "language": "python",
            "clearContext": True
        })

        for event in response["stream"]:
            code_execute_result = json.dumps(event["result"])
        
        analysis_results = json.loads(code_execute_result)

        return {"success": True, "result": str(analysis_results)}

    except Exception as e:
        return {"success": False, "error": str(e)}


@app.post("/tools/store_user_preferences")
async def store_user_preferences(req: PreferencesRequest):
    try:
        client = MemoryClient(region_name=AWS_REGION)
        client.save_turn(
            memory_id=MEMORY_ID,
            actor_id="user123",
            session_id="session456",
            user_input=f"My preferences: {req.preferences}",
            agent_response="Preferences saved"
        )
        return {"success": True, "result": f"Preferences stored: {req.preferences}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.post("/tools/get_activity_preferences")
async def get_activity_preferences():
    try:
        client = MemoryClient(region_name=AWS_REGION)
        response = client.retrieve_memories(
            memory_id=MEMORY_ID,
            query="What are the user's activity preferences and interests?",
            max_results=5
        )
        
        if response and len(response) > 0:
            preferences = "\n".join([str(item) for item in response])
            return {"success": True, "result": f"User preferences: {preferences}"}
        else:
            return {"success": True, "result": "No preferences stored. Default: outdoor activities, hiking, beaches, museums."}
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.post("/tools/store_activity_plan")
async def store_activity_plan(req: PlanRequest):
    try:
        client = MemoryClient(region_name=AWS_REGION)
        client.save_turn(
            memory_id=MEMORY_ID,
            actor_id="user123",
            session_id="session456",
            user_input=f"Plan for {req.city}",
            agent_response=req.plan
        )
        return {"success": True, "result": f"Activity plan stored in memory for {req.city}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.get("/health")
async def health():
    return {"status": "healthy"}


@app.post("/mcp")
async def mcp_endpoint(request: dict):
    """Handle MCP protocol requests"""
    method = request.get("method")
    
    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": request.get("id"),
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "agent-core-tools", "version": "1.0.0"}
            }
        }
    
    elif method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": request.get("id"),
            "result": {
                "tools": [
                    {"name": "get_weather_data", "description": "Get weather data for a city using browser automation", "inputSchema": {"type": "object", "properties": {"city": {"type": "string"}}, "required": ["city"]}},
                    {"name": "generate_analysis_code", "description": "Generate Python code for weather classification", "inputSchema": {"type": "object", "properties": {"weather_data": {"type": "string"}}, "required": ["weather_data"]}},
                    {"name": "execute_code", "description": "Execute Python code using Agent Core Code Interpreter", "inputSchema": {"type": "object", "properties": {"python_code": {"type": "string"}}, "required": ["python_code"]}},
                    {"name": "store_user_preferences", "description": "Store user activity preferences in memory", "inputSchema": {"type": "object", "properties": {"preferences": {"type": "string"}}, "required": ["preferences"]}},
                    {"name": "get_activity_preferences", "description": "Get user activity preferences from memory", "inputSchema": {"type": "object", "properties": {}}},
                    {"name": "store_activity_plan", "description": "Store the activity plan in memory", "inputSchema": {"type": "object", "properties": {"city": {"type": "string"}, "plan": {"type": "string"}}, "required": ["city", "plan"]}}
                ]
            }
        }
    
    elif method == "tools/call":
        tool_name = request.get("params", {}).get("name")
        arguments = request.get("params", {}).get("arguments", {})
        
        if tool_name == "get_weather_data":
            result = await get_weather_data(WeatherRequest(**arguments))
        elif tool_name == "generate_analysis_code":
            result = await generate_analysis_code(CodeRequest(**arguments))
        elif tool_name == "execute_code":
            result = await execute_code(ExecuteRequest(**arguments))
        elif tool_name == "store_user_preferences":
            result = await store_user_preferences(PreferencesRequest(**arguments))
        elif tool_name == "get_activity_preferences":
            result = await get_activity_preferences()
        elif tool_name == "store_activity_plan":
            result = await store_activity_plan(PlanRequest(**arguments))
        else:
            return {"jsonrpc": "2.0", "id": request.get("id"), "error": {"code": -32601, "message": f"Tool not found: {tool_name}"}}
        
        return {
            "jsonrpc": "2.0",
            "id": request.get("id"),
            "result": {"content": [{"type": "text", "text": str(result)}]}
        }
    
    return {"jsonrpc": "2.0", "id": request.get("id"), "error": {"code": -32601, "message": f"Method not found: {method}"}}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
