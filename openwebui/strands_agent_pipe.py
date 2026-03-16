"""
title: Strands Agent Pipe with OAuth Token Forwarding
author: Agent Core Team
version: 1.1.0

This Pipe function retrieves the OAuth token from OpenWebUI's server-side session
and forwards it to the Strands Agent API for MCP tool authorization via AgentGateway.
"""

import json
import logging
import time
import traceback
from typing import AsyncGenerator, Optional, Callable, Awaitable, Any, Dict, List

import httpx
from pydantic import BaseModel, Field
from starlette.requests import Request

logger = logging.getLogger(__name__)


class Pipe:
    """
    OpenWebUI Pipe that forwards OAuth tokens to Strands Agent for MCP authorization.
    """

    class Valves(BaseModel):
        """Configuration options for the pipe."""
        STRANDS_AGENT_URL: str = Field(
            default="http://strands-agent-v5.agent-core-infra.svc.cluster.local:8000",
            description="Base URL for Strands Agent API"
        )
        model_name_prefix: str = Field(
            default="Strands: ",
            description="Prefix for model names in the dropdown"
        )
        timeout_seconds: float = Field(
            default=120.0,
            description="Timeout for API requests in seconds"
        )
        debug_mode: bool = Field(
            default=False,
            description="Enable debug mode for additional logging (logs to server, not UI)"
        )

    def __init__(self) -> None:
        self.type: str = "pipe"
        self.id: str = "strands_agent_oauth"
        self.valves = self.Valves()
        self.name: str = self.valves.model_name_prefix

    async def on_startup(self) -> None:
        """Called when the server starts."""
        logger.info(f"Strands Agent Pipe starting up, connecting to: {self.valves.STRANDS_AGENT_URL}")

    async def on_shutdown(self) -> None:
        """Called when the server stops."""
        logger.info("Strands Agent Pipe shutting down")

    async def on_valves_updated(self) -> None:
        """Called when valves are updated."""
        logger.info(f"Valves updated, new URL: {self.valves.STRANDS_AGENT_URL}")

    def pipes(self) -> List[Dict[str, str]]:
        """Return available models/pipes."""
        return [
            {
                "id": "strands-weather-agent",
                "name": "Weather Activity Planner"
            }
        ]

    async def pipe(
        self,
        body: Dict[str, Any],
        __request__: Optional[Request] = None,
        __user__: Optional[Dict[str, Any]] = None,
        __event_emitter__: Optional[Callable[[Dict[str, Any]], Awaitable[None]]] = None,
        __event_call__: Optional[Callable[[Dict[str, Any]], Awaitable[Dict[str, Any]]]] = None,
    ) -> AsyncGenerator[str, None]:
        """
        Main pipe method that forwards requests to Strands Agent with OAuth token.
        """
        logger.info("Strands Agent Pipe: Processing request")

        if __request__ is None:
            yield "Error: Request object not available"
            return

        # Debug logging (to server logs only, not to UI)
        if self.valves.debug_mode:
            logger.info(f"Cookies available: {list(__request__.cookies.keys())}")
            logger.info(f"User info: {__user__}")
            if __user__ and "oauth" in __user__:
                logger.info(f"OAuth info in user: {list(__user__['oauth'].keys()) if isinstance(__user__['oauth'], dict) else 'present'}")

        # Extract OAuth token
        oauth_token = self._extract_oauth_token(__request__, __user__)
        
        if self.valves.debug_mode:
            logger.info(f"OAuth token found: {oauth_token is not None}")
            if oauth_token:
                logger.info(f"Token length: {len(oauth_token)}, parts: {len(oauth_token.split('.'))}")

        if oauth_token is None:
            yield (
                "🔐 **Authentication Required**\n\n"
                "No OAuth token found. Please sign out and sign back in with Keycloak.\n\n"
                "If the problem persists, your session may have expired."
            )
            return

        # Build headers with OAuth token
        headers = self._build_headers(__request__, __user__, oauth_token)

        # Extract model ID from body
        model_id = body.get("model", "strands-weather-agent")
        if "." in model_id:
            model_id = model_id.split(".")[-1]

        # Prepare payload - request non-streaming for simpler handling
        payload = {**body, "model": model_id, "stream": False}

        url = f"{self.valves.STRANDS_AGENT_URL}/v1/chat/completions"
        
        if self.valves.debug_mode:
            logger.info(f"Calling {url}")

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    url=url,
                    json=payload,
                    headers=headers,
                    timeout=self.valves.timeout_seconds,
                    follow_redirects=True,
                )

                if response.status_code == 401:
                    yield (
                        "🔐 **Authentication Failed**\n\n"
                        "Your session has expired or is invalid. "
                        "Please sign out and sign back in."
                    )
                    return

                if response.status_code == 403:
                    yield (
                        "🚫 **Access Denied**\n\n"
                        "You don't have permission to use this tool. "
                        "Please contact your administrator for access."
                    )
                    return

                response.raise_for_status()

                # Parse JSON response
                response_json = response.json()
                
                if "choices" in response_json and len(response_json["choices"]) > 0:
                    content = response_json["choices"][0].get("message", {}).get("content", "")
                    # Yield the content directly - OpenWebUI will render markdown
                    yield content
                else:
                    yield "No response received from the agent."

        except httpx.TimeoutException:
            logger.error("Request to Strands Agent timed out")
            yield (
                "⏱️ **Request Timeout**\n\n"
                "The request took too long to complete. "
                "Please try again or simplify your query."
            )
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error: {e.response.status_code} - {e.response.text}")
            yield f"❌ **Error**: HTTP {e.response.status_code}\n\n{e.response.text[:500]}"
        except Exception as e:
            logger.exception(f"Unexpected error in pipe: {e}")
            error_msg = str(e) if self.valves.debug_mode else "An unexpected error occurred"
            yield f"❌ **Error**: {error_msg}"

    def _extract_oauth_token(self, request: Request, user: Optional[Dict[str, Any]]) -> Optional[str]:
        """Extract OAuth token from various sources."""
        
        # 1. Check if user object contains OAuth token (OpenWebUI may inject it)
        if user:
            # Check for oauth_id_token in user info
            if "oauth_id_token" in user:
                logger.info("Found oauth_id_token in user object")
                return user["oauth_id_token"]
            
            # Check for nested oauth object
            if "oauth" in user and isinstance(user["oauth"], dict):
                if "id_token" in user["oauth"]:
                    logger.info("Found id_token in user.oauth")
                    return user["oauth"]["id_token"]
                if "access_token" in user["oauth"]:
                    logger.info("Found access_token in user.oauth")
                    return user["oauth"]["access_token"]
        
        # 2. Try cookies
        logger.info(f"Checking cookies: {list(request.cookies.keys())}")
        
        # Try oauth_id_token cookie
        token = request.cookies.get("oauth_id_token")
        if token:
            logger.info("Found OAuth token in oauth_id_token cookie")
            return token

        # Try oauth_access_token cookie
        token = request.cookies.get("oauth_access_token")
        if token:
            logger.info("Found OAuth token in oauth_access_token cookie")
            return token
        
        # Try token cookie
        token = request.cookies.get("token")
        if token and len(token.split(".")) == 3:
            logger.info("Found JWT in token cookie")
            return token

        # 3. Try Authorization header (last resort)
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
            if len(token.split(".")) == 3:
                logger.info("Found JWT in Authorization header")
                return token
            else:
                logger.warning(f"Authorization token is not a JWT ({len(token.split('.'))} parts)")

        logger.warning("No OAuth token found")
        return None

    def _build_headers(
        self, 
        request: Request, 
        user: Optional[Dict[str, Any]], 
        oauth_token: str
    ) -> Dict[str, str]:
        """Build headers for the downstream request."""
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {oauth_token}",
        }

        # Forward user info if available
        if user:
            if user.get("name"):
                headers["X-User-Name"] = user["name"]
            if user.get("id"):
                headers["X-User-Id"] = user["id"]
            if user.get("email"):
                headers["X-User-Email"] = user["email"]
            if user.get("role"):
                headers["X-User-Role"] = user["role"]

        # Forward trace headers
        for header in ["traceparent", "tracestate", "x-request-id"]:
            if header in request.headers:
                headers[header] = request.headers[header]

        return headers

    def _sanitize_headers(self, headers: Dict[str, str]) -> Dict[str, str]:
        """Remove sensitive data from headers for logging."""
        sanitized = {}
        for key, value in headers.items():
            if key.lower() == "authorization":
                sanitized[key] = "Bearer [REDACTED]"
            else:
                sanitized[key] = value
        return sanitized
