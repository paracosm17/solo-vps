[CmdletBinding()]
param(
    [string]$KeyPath = (Join-Path $env:USERPROFILE ".config\solo-vps\age-key.txt"),
    [string]$StateRoot = (Join-Path $env:LOCALAPPDATA "solo-vps\state"),
    [string]$PolicyPath = "",
    [string]$OutputPath = ""
)

$ErrorActionPreference = "Stop"

function Resolve-SoloVpsTool {
    param([Parameter(Mandatory = $true)][string]$Name)
    $command = Get-Command "$Name.exe" -ErrorAction SilentlyContinue
    if ($command) { return $command.Source }
    $managed = Join-Path $env:LOCALAPPDATA "solo-vps\bin\$Name.exe"
    if (Test-Path -LiteralPath $managed -PathType Leaf) { return $managed }
    throw "$Name.exe is not installed. Run .\scripts\windows\install-secrets-tools.ps1 first."
}

function Quote-ProcessArgument {
    param([Parameter(Mandatory = $true)][string]$Value)
    if ($Value.Contains('"')) { throw "Unsupported quote character in process argument." }
    return '"' + $Value + '"'
}

function Invoke-TextProcess {
    param(
        [Parameter(Mandatory = $true)][string]$FilePath,
        [Parameter(Mandatory = $true)][string]$Arguments,
        [Parameter(Mandatory = $true)][string]$InputText
    )
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $FilePath
    $psi.Arguments = $Arguments
    $psi.UseShellExecute = $false
    $psi.RedirectStandardInput = $true
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $psi.CreateNoWindow = $true
    $process = New-Object System.Diagnostics.Process
    $process.StartInfo = $psi
    if (-not $process.Start()) { throw "Could not start $FilePath" }
    $process.StandardInput.Write($InputText)
    $process.StandardInput.Close()
    $stdout = $process.StandardOutput.ReadToEnd()
    $stderr = $process.StandardError.ReadToEnd()
    $process.WaitForExit()
    if ($process.ExitCode -ne 0) {
        throw "SOPS process failed with exit code $($process.ExitCode); secret-bearing stderr was suppressed."
    }
    return $stdout
}

function Read-SecureText {
    param([Parameter(Mandatory = $true)][string]$Prompt)
    $secure = Read-Host $Prompt -AsSecureString
    $ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
    try { return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr) }
    finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr) }
}

function Assert-PrometheusUrl {
    param([Parameter(Mandatory = $true)][string]$Value)
    $uri = $null
    if (-not [Uri]::TryCreate($Value, [UriKind]::Absolute, [ref]$uri)) { throw "PROMETHEUS_URL must be an absolute HTTPS URL." }
    if ($uri.Scheme -ne "https" -or [string]::IsNullOrWhiteSpace($uri.Host)) { throw "PROMETHEUS_URL must use HTTPS and contain a host." }
    if (-not $uri.AbsolutePath.TrimEnd("/").EndsWith("/api/prom/push")) { throw "PROMETHEUS_URL must end with /api/prom/push." }
    if ($uri.Query -or $uri.Fragment -or -not [string]::IsNullOrEmpty($uri.UserInfo)) { throw "PROMETHEUS_URL must not contain credentials, query parameters, or a fragment." }
}

$sops = Resolve-SoloVpsTool -Name "sops"
$fullStateRoot = [System.IO.Path]::GetFullPath($StateRoot)
if (-not $PolicyPath) { $PolicyPath = Join-Path $fullStateRoot "sops\.sops.yaml" }
if (-not $OutputPath) { $OutputPath = Join-Path $fullStateRoot "secrets\metrics.enc.yaml" }
$fullPolicyPath = [System.IO.Path]::GetFullPath($PolicyPath)
$fullOutputPath = [System.IO.Path]::GetFullPath($OutputPath)

if (-not (Test-Path -LiteralPath $fullPolicyPath -PathType Leaf)) {
    throw "Persistent SOPS policy is missing: $fullPolicyPath. Run .\scripts\windows\init-sops-policy.ps1 first."
}
if (Test-Path -LiteralPath $fullOutputPath) {
    $fullKeyPath = [System.IO.Path]::GetFullPath($KeyPath)
    $testScript = Join-Path $PSScriptRoot "test-metrics-secrets.ps1"
    try {
        & $testScript -KeyPath $fullKeyPath -StateRoot $fullStateRoot -PolicyPath $fullPolicyPath -EncryptedPath $fullOutputPath
    }
    catch {
        throw "An encrypted metrics bundle already exists but it cannot be validated with the current age key. If you are intentionally repeating setup and can enter the Grafana credentials again, run .\scripts\windows\init-sops-policy.ps1 -StartFresh first. The old ciphertext will be archived, not deleted. Validation error: $($_.Exception.Message)"
    }
    Write-Host "PASS encrypted metrics secret bundle already exists; reusing it"
    Write-Host "  existing ciphertext replaced: no"
    Write-Host "  to enter new credentials: use the token-rotation workflow or start fresh explicitly"
    return
}

Write-Host "Enter the Grafana Cloud Metrics connection values. The access-policy token is hidden and will not be printed."
$prometheusUrl = (Read-Host "Grafana Cloud Prometheus remote write URL").Trim()
$prometheusUsername = (Read-Host "Grafana Cloud Metrics user ID").Trim()
$apiKey = Read-SecureText -Prompt "Grafana Cloud access-policy token (metrics:write)"
Assert-PrometheusUrl -Value $prometheusUrl
if ([string]::IsNullOrWhiteSpace($prometheusUsername) -or [string]::IsNullOrEmpty($apiKey)) { throw "Metrics user ID and access-policy token must not be empty." }
if ($prometheusUsername -notmatch '^[0-9]+$') { throw "Grafana Cloud Metrics user ID must be numeric." }
foreach ($value in @($prometheusUrl, $prometheusUsername, $apiKey)) {
    if ($value -match "[`r`n`0]") { throw "Metrics credential values must be single-line strings." }
}

$payload = [ordered]@{
    PROMETHEUS_URL = $prometheusUrl
    PROMETHEUS_USERNAME = $prometheusUsername
    GRAFANA_CLOUD_METRICS_API_KEY = $apiKey
}
$json = $payload | ConvertTo-Json -Compress
$args = @(
    "--config", (Quote-ProcessArgument $fullPolicyPath),
    "encrypt",
    "--filename-override", (Quote-ProcessArgument "secrets/metrics.enc.yaml"),
    "--input-type", "json",
    "--output-type", "yaml"
) -join " "
$encrypted = Invoke-TextProcess -FilePath $sops -Arguments $args -InputText $json
if ([string]::IsNullOrWhiteSpace($encrypted)) { throw "SOPS returned empty ciphertext." }
foreach ($value in @($prometheusUrl, $prometheusUsername, $apiKey)) {
    if ($value -and $encrypted.Contains($value)) { throw "SOPS output unexpectedly contains a plaintext metrics value." }
}

$parent = Split-Path -Parent $fullOutputPath
New-Item -ItemType Directory -Force -Path $parent | Out-Null
$temporary = Join-Path $parent ("." + [System.IO.Path]::GetFileName($fullOutputPath) + "." + [guid]::NewGuid().ToString("N"))
try {
    [System.IO.File]::WriteAllText($temporary, $encrypted, [System.Text.UTF8Encoding]::new($false))
    Move-Item -LiteralPath $temporary -Destination $fullOutputPath
}
finally {
    Remove-Item -LiteralPath $temporary -Force -ErrorAction SilentlyContinue
    $apiKey = $null
    $json = $null
}

Write-Host "PASS encrypted metrics secret bundle created"
Write-Host "  ciphertext: $fullOutputPath"
Write-Host "  plaintext file created: no"
Write-Host "  source checkout mutated: no"
