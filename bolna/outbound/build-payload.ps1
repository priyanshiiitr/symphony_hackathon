# Builds agent_payload.json from template + graph + tools, substituting BASE_URL.
param(
    [string]$BaseUrl = ""
)

$ErrorActionPreference = "Stop"
$here = $PSScriptRoot

if (-not $BaseUrl) {
    $urlFile = Join-Path $here "..\..\scripts\PUBLIC_URL.txt"
    if (Test-Path $urlFile) {
        $BaseUrl = (Get-Content $urlFile -Raw).Trim()
    }
}
if (-not $BaseUrl) {
    throw "Pass -BaseUrl or save scripts/PUBLIC_URL.txt from the tunnel"
}
$BaseUrl = $BaseUrl.TrimEnd("/")

$template = Get-Content (Join-Path $here "agent_payload.template.json") -Raw | ConvertFrom-Json
$graph = Get-Content (Join-Path $here "graph_nodes.json") -Raw | ConvertFrom-Json
$toolsDoc = Get-Content (Join-Path $here "tools.json") -Raw | ConvertFrom-Json

# Merge graph into llm_config
$llm = $template.agent_config.tasks[0].tools_config.llm_agent.llm_config
foreach ($p in $graph.PSObject.Properties) {
    $llm | Add-Member -NotePropertyName $p.Name -NotePropertyValue $p.Value -Force
}

# Tools with BASE_URL substituted
$toolsJson = ($toolsDoc.tools | ConvertTo-Json -Depth 20)
$paramsRaw = $toolsDoc.tools_params | ConvertTo-Json -Depth 20
$paramsRaw = $paramsRaw -replace '\{\{BASE_URL\}\}', $BaseUrl
$params = $paramsRaw | ConvertFrom-Json

$template.agent_config.tasks[0].tools_config.api_tools.tools = $toolsDoc.tools
$template.agent_config.tasks[0].tools_config.api_tools.tools_params = $params

$outPath = Join-Path $here "agent_payload.json"
$json = $template | ConvertTo-Json -Depth 40
# utf8 no BOM — Bolna/Python reject BOM
[System.IO.File]::WriteAllText($outPath, $json, [System.Text.UTF8Encoding]::new($false))
Write-Host "Wrote $outPath"
Write-Host "BASE_URL=$BaseUrl"
return $outPath
