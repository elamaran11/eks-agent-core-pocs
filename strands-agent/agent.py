import os
import json
import boto3
from typing import Dict, Any, List

class StrandsAgent:
    def __init__(self):
        self.region = os.environ.get('AWS_REGION', 'us-east-1')
        self.memory_kb_id = os.environ.get('AGENT_MEMORY_KB_ID')
        self.code_interpreter_id = os.environ.get('CODE_INTERPRETER_ID')
        self.browser_id = os.environ.get('BROWSER_ID')
        
        self.bedrock_agent = boto3.client('bedrock-agent-runtime', region_name=self.region)
        self.bedrock_runtime = boto3.client('bedrock-runtime', region_name=self.region)
        
    def retrieve_from_memory(self, query: str) -> List[Dict]:
        """Retrieve relevant information from Agent Core Memory"""
        response = self.bedrock_agent.retrieve(
            knowledgeBaseId=self.memory_kb_id,
            retrievalQuery={'text': query}
        )
        return response.get('retrievalResults', [])
    
    def execute_code(self, code: str) -> Dict[str, Any]:
        """Execute code using Agent Core Code Interpreter"""
        response = self.bedrock_agent.invoke_agent_core_tool(
            toolId=self.code_interpreter_id,
            input={'code': code}
        )
        return response
    
    def browse_web(self, url: str) -> Dict[str, Any]:
        """Browse web using Agent Core Browser"""
        response = self.bedrock_agent.invoke_agent_core_tool(
            toolId=self.browser_id,
            input={'url': url}
        )
        return response
    
    def invoke_llm(self, prompt: str, context: str = "") -> str:
        """Invoke Bedrock LLM"""
        full_prompt = f"{context}\n\nUser Query: {prompt}" if context else prompt
        
        body = json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 4096,
            "messages": [{"role": "user", "content": full_prompt}]
        })
        
        response = self.bedrock_runtime.invoke_model(
            modelId='anthropic.claude-3-sonnet-20240229-v1:0',
            body=body
        )
        
        result = json.loads(response['body'].read())
        return result['content'][0]['text']
    
    def run_weather_example(self):
        """Run weather agent example"""
        print("Starting Weather Agent Example...")
        
        # Step 1: Get weather data using code interpreter
        weather_code = """
import requests
response = requests.get('https://api.weather.gov/gridpoints/TOP/31,80/forecast')
data = response.json()
forecast = data['properties']['periods'][0]
print(f"Temperature: {forecast['temperature']}°{forecast['temperatureUnit']}")
print(f"Forecast: {forecast['detailedForecast']}")
"""
        print("\n1. Executing weather data retrieval...")
        code_result = self.execute_code(weather_code)
        print(f"Code execution result: {code_result}")
        
        # Step 2: Retrieve context from memory
        print("\n2. Retrieving context from memory...")
        memory_results = self.retrieve_from_memory("weather forecast information")
        context = "\n".join([r.get('content', {}).get('text', '') for r in memory_results])
        
        # Step 3: Browse weather website
        print("\n3. Browsing weather website...")
        browse_result = self.browse_web("https://weather.gov")
        
        # Step 4: Generate response using LLM
        print("\n4. Generating final response...")
        prompt = "Provide a weather summary based on the data retrieved"
        response = self.invoke_llm(prompt, context)
        print(f"\nFinal Response:\n{response}")
        
        return response

if __name__ == "__main__":
    agent = StrandsAgent()
    agent.run_weather_example()
