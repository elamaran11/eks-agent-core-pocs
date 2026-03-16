# OpenWebUI Pipe Function for OAuth Token Forwarding

This Pipe function forwards OAuth tokens from OpenWebUI to the Strands Agent API, enabling MCP tool authorization via AgentGateway.

## Installation

### Step 1: Enable OAuth ID Token Cookie

Make sure your OpenWebUI deployment has this environment variable:

```yaml
- name: ENABLE_OAUTH_ID_TOKEN_COOKIE
  value: "true"
```

This stores the Keycloak JWT in a cookie that the Pipe can access.

### Step 2: Install the Pipe Function in OpenWebUI

1. Open OpenWebUI in your browser
2. Go to **Workspace** → **Functions** (or click the puzzle icon)
3. Click **+ Create Function**
4. Select **Pipe** as the function type
5. Copy the contents of `strands_agent_pipe.py` into the editor
6. Click **Save**

### Step 3: Configure the Pipe

After saving, click on the function to configure:

1. **STRANDS_AGENT_URL**: Set to your Strands Agent service URL
   - Default: `http://strands-agent-v5.agent-core-infra.svc.cluster.local:8000`
   
2. **timeout_seconds**: Adjust if your queries take longer
   - Default: `120.0`

3. **debug_mode**: Enable for troubleshooting
   - Default: `false`

### Step 4: Use the Pipe

1. In the chat interface, select the model dropdown
2. Look for **"Strands: Weather Activity Planner"**
3. Select it and start chatting

## How It Works

```
┌──────────┐     ┌─────────────┐     ┌──────────────┐     ┌─────────────────┐
│  User    │────▶│  OpenWebUI  │────▶│ Strands Agent│────▶│  AgentGateway   │
│          │     │  (Pipe)     │     │              │     │  (JWT Auth)     │
└──────────┘     └─────────────┘     └──────────────┘     └─────────────────┘
                       │                    │
                       │  oauth_id_token    │  Authorization:
                       │  cookie            │  Bearer <JWT>
                       └────────────────────┘
```

1. User logs in via Keycloak → OpenWebUI stores JWT in `oauth_id_token` cookie
2. User sends message → Pipe reads JWT from cookie
3. Pipe forwards request to Strands Agent with `Authorization: Bearer <JWT>` header
4. Strands Agent passes JWT to MCP client
5. AgentGateway validates JWT and authorizes tool access

## Troubleshooting

### "No OAuth token found"

- Sign out and sign back in to refresh your Keycloak session
- Verify `ENABLE_OAUTH_ID_TOKEN_COOKIE=true` in OpenWebUI deployment
- Check browser cookies for `oauth_id_token`

### "Authentication Failed" (401)

- Your Keycloak session may have expired
- Sign out and sign back in

### "Access Denied" (403)

- Your Keycloak user doesn't have the required role
- Contact your administrator to add you to the appropriate group

### Timeout errors

- Increase `timeout_seconds` in Pipe configuration
- Check if MCP servers are healthy

### Debug Mode

Enable `debug_mode` in the Pipe configuration to see:
- Whether OAuth token is present
- Request headers being sent
- Response details

## Testing

After installation, try:

```
What should I do this weekend in Seattle?
```

If authorization is working, the agent will use MCP tools (browser, code interpreter, memory) to plan activities.
