from strands import Agent, tool
from strands_tools import use_aws
from typing import Dict, Any
import json
import os
import asyncio
from contextlib import suppress

from bedrock_agentcore.tools.browser_client import BrowserClient
from browser_use import Agent as BrowserAgent
from browser_use.browser.session import BrowserSession
from browser_use.browser import BrowserProfile
from langchain_aws import ChatBedrockConverse
from bedrock_agentcore.tools.code_interpreter_client import CodeInterpreter
from bedrock_agentcore.memory import MemoryClient
from rich.console import Console
import re

console = Console()

# Configuration from environment variables
BROWSER_ID = os.getenv('BROWSER_ID')
CODE_INTERPRETER_ID = os.getenv('CODE_INTERPRETER_ID')
MEMORY_ID = os.getenv('MEMORY_ID')
RESULTS_BUCKET = os.getenv('RESULTS_BUCKET', 'weather-results-bucket')
AWS_REGION = os.getenv('AWS_REGION', 'us-east-1')

# Check which capabilities are enabled
HAS_BROWSER = bool(BROWSER_ID)
HAS_CODE_INTERPRETER = bool(CODE_INTERPRETER_ID)
HAS_MEMORY = bool(MEMORY_ID)

console.print(f"[cyan]🔧 Enabled Capabilities:[/cyan]")
console.print(f"  Browser: {'✅' if HAS_BROWSER else '❌'}")
console.print(f"  Code Interpreter: {'✅' if HAS_CODE_INTERPRETER else '❌'}")
console.print(f"  Memory: {'✅' if HAS_MEMORY else '❌'}")

async def run_browser_task(browser_session, bedrock_chat, task: str) -> str:
    """Run a browser automation task"""
    try:
        console.print(f"[blue]🤖 Executing browser task:[/blue] {task[:100]}...")
        
        agent = BrowserAgent(task=task, llm=bedrock_chat, browser=browser_session)
        result = await agent.run()
        console.print("[green]✅ Browser task completed![/green]")
        
        if 'done' in result.last_action() and 'text' in result.last_action()['done']:
            return result.last_action()['done']['text']
        else:
            raise ValueError("NO Data")
            
    except Exception as e:
        console.print(f"[red]❌ Browser task error: {e}[/red]")
        raise

async def initialize_browser_session():
    """Initialize Browser session with AgentCore"""
    try:
        client = BrowserClient(AWS_REGION)
        client.start(identifier=BROWSER_ID)
        
        ws_url, headers = client.generate_ws_headers()
        console.print(f"[cyan]🔗 Browser WebSocket URL: {ws_url[:50]}...[/cyan]")
        
        browser_profile = BrowserProfile(headers=headers, timeout=150000)
        browser_session = BrowserSession(cdp_url=ws_url, browser_profile=browser_profile, keep_alive=True)
        
        console.print("[cyan]🔄 Initializing browser session...[/cyan]")
        await browser_session.start()
        
        bedrock_chat = ChatBedrockConverse(
            model_id="us.anthropic.claude-3-7-sonnet-20250219-v1:0",
            region_name=AWS_REGION
        )
        
        console.print("[green]✅ Browser session ready[/green]")
        return browser_session, bedrock_chat, client
        
    except Exception as e:
        console.print(f"[red]❌ Failed to initialize browser: {e}[/red]")
        raise

@tool
async def get_weather_data(city: str) -> Dict[str, Any]:
    """Get weather data for a city using browser automation"""
    if not HAS_BROWSER:
        return {"status": "error", "content": [{"text": "Browser capability not enabled"}]}
    
    browser_session = None
    
    try:
        console.print(f"[cyan]🌐 Getting weather data for {city}[/cyan]")
        
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
        console.print(f"[red]❌ Error getting weather data: {e}[/red]")
        return {"status": "error", "content": [{"text": f"Error: {str(e)}"}]}
        
    finally:
        if browser_session:
            with suppress(Exception):
                await browser_session.close()

@tool
def generate_analysis_code(weather_data: str) -> Dict[str, Any]:
    """Generate Python code for weather classification"""
    try:
        query = f"""Create Python code to classify weather days as GOOD/OK/POOR:
        Rules: GOOD: 65-80°F clear, OK: 55-85°F partly cloudy, POOR: <55°F or >85°F
        Weather data: {weather_data}
        Return code that outputs list of tuples: [('2025-09-16', 'GOOD'), ...]"""
        
        agent = Agent()
        result = agent(query)
        
        pattern = r'```(?:json|python)\n(.*?)\n```'
        match = re.search(pattern, result.message['content'][0]['text'], re.DOTALL)
        python_code = match.group(1).strip() if match else result.message['content'][0]['text']
        
        return {"status": "success", "content": [{"text": python_code}]}
    except Exception as e:
        return {"status": "error", "content": [{"text": f"Error: {str(e)}"}]}

@tool
def execute_code(python_code: str) -> Dict[str, Any]:
    """Execute Python code using AgentCore Code Interpreter"""
    if not HAS_CODE_INTERPRETER:
        return {"status": "error", "content": [{"text": "Code Interpreter capability not enabled"}]}
    
    try:
        code_client = CodeInterpreter(AWS_REGION)
        code_client.start(identifier=CODE_INTERPRETER_ID)

        response = code_client.invoke("executeCode", {
            "code": python_code,
            "language": "python",
            "clearContext": True
        })

        for event in response["stream"]:
            code_execute_result = json.dumps(event["result"])
        
        analysis_results = json.loads(code_execute_result)
        console.print("Analysis results:", analysis_results)

        return {"status": "success", "content": [{"text": str(analysis_results)}]}

    except Exception as e:
        return {"status": "error", "content": [{"text": f"Error: {str(e)}"}]}

@tool
def get_activity_preferences() -> Dict[str, Any]:
    """Get activity preferences from memory"""
    if not HAS_MEMORY:
        return {"status": "success", "content": [{"text": "Memory capability not enabled. Using default preferences."}]}
    
    try:
        client = MemoryClient(region_name=AWS_REGION)
        response = client.list_events(
            memory_id=MEMORY_ID,
            actor_id="user123",
            session_id="session456",
            max_results=50,
            include_payload=True
        )
        
        preferences = response[0]["payload"][0]['blob'] if response else "No preferences found"
        return {"status": "success", "content": [{"text": preferences}]}
    except Exception as e:
        return {"status": "error", "content": [{"text": f"Error: {str(e)}"}]}

def create_weather_agent() -> Agent:
    """Create the weather agent with all tools"""
    system_prompt = f"""You are a Weather-Based Activity Planning Assistant.

    When a user asks about activities for a location:
    1. Extract city from query
    2. Call get_weather_data(city)
    3. Call generate_analysis_code(weather_data)
    4. Call execute_code(python_code)
    5. Call get_activity_preferences()
    6. Generate Activity Recommendations
    7. Store results.md in S3 Bucket: {RESULTS_BUCKET} via use_aws tool
    
    IMPORTANT: Provide complete recommendations and end your response."""
    
    return Agent(
        tools=[get_weather_data, generate_analysis_code, execute_code, get_activity_preferences, use_aws],
        system_prompt=system_prompt,
        name="WeatherActivityPlanner"
    )

async def async_main(query=None):
    """Main async function"""
    console.print("🌤️ Weather-Based Activity Planner")
    console.print("=" * 30)
    
    agent = create_weather_agent()
    
    query = query or "What should I do this weekend in Richmond VA?"
    console.print(f"\n[bold blue]🔍 Query:[/bold blue] {query}")
    
    try:
        os.environ["BYPASS_TOOL_CONSENT"] = "True"
        result = agent(query)
        return {"status": "completed", "result": result.message['content'][0]['text']}
        
    except Exception as e:
        console.print(f"[red]❌ Error: {e}[/red]")
        return {"status": "error", "error": str(e)}

if __name__ == "__main__":
    console.print("🚀 Strands Agent Running on EKS")
    console.print("Waiting for requests...")
    console.print("Press Ctrl+C to exit")
    
    # Keep container running
    import time
    while True:
        time.sleep(3600)
