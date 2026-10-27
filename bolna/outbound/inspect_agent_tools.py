import json
import os
import urllib.request

key = os.environ["BOLNA_API_KEY"]
req = urllib.request.Request(
    "https://api.bolna.ai/v2/agent/576128ab-85dc-454e-ae72-052ff8066a52",
    headers={"Authorization": f"Bearer {key}"},
)
agent = json.loads(urllib.request.urlopen(req).read().decode())
tasks = agent.get("tasks") or agent.get("agent_config", {}).get("tasks")
params = tasks[0]["tools_config"]["api_tools"]["tools_params"]
print(json.dumps(params, indent=2, ensure_ascii=False))
