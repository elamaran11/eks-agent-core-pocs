# Agent Example

Single declarative agent that uses Agent Core MCP tools.

## Deploy

```bash
kubectl apply -f examples/agent.yaml
```

## Test

```bash
kubectl exec -it -n agent-core-infra deployment/weather-agent -- python -c "
from kagent import invoke_agent
result = invoke_agent(
    agent_name='weather-agent',
    input='What should I do this weekend in Tampa, FL?'
)
print(result)
"
```

## The 6 MCP Tools

1. `get_weather_data(city)` - Browser automation
2. `generate_analysis_code(weather_data)` - Code generation  
3. `execute_code(python_code)` - Code execution
4. `store_user_preferences(preferences)` - Memory write
5. `get_activity_preferences()` - Memory read
6. `store_activity_plan(city, plan)` - Memory write

## How It Works

```yaml
spec:
  type: Declarative
  declarative:
    tools:
      - type: McpServer
        mcpServer:
          kind: RemoteMCPServer
          name: agent-core-tools-v6-kagent
          toolNames:  # Explicit tool list
            - get_weather_data
            - generate_analysis_code
            - execute_code
            - store_user_preferences
            - get_activity_preferences
            - store_activity_plan
```

KAgent loads the 6 tools from the RemoteMCPServer and makes them available to the agent.
