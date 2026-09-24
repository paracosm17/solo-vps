[CmdletBinding()]
param(
    [string]$KeyPath = (Join-Path $env:USERPROFILE ".config\solo-vps\age-key.txt"),
    [string]$StateRoot = (Join-Path $env:LOCALAPPDATA "solo-vps\state"),
    [string]$PolicyPath = "",
    [string]$EncryptedPath = ""
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

function Invoke-SopsDecrypt {
    param([string]$Sops, [string]$Policy, [string]$Encrypted, [string]$Key)
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $Sops
    $psi.Arguments = @(
        "--config", (Quote-ProcessArgument $Policy),
        "decrypt", "--input-type", "yaml", "--output-type", "json", (Quote-ProcessArgument $Encrypted)
    ) -join " "
    $psi.UseShellExecute = $false
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $psi.CreateNoWindow = $true
    $psi.EnvironmentVariables["SOPS_AGE_KEY_FILE"] = $Key
    $process = New-Object System.Diagnostics.Process
    $process.StartInfo = $psi
    if (-not $process.Start()) { throw "Could not start sops.exe" }
    $stdout = $process.StandardOutput.ReadToEnd()
    $stderr = $process.StandardError.ReadToEnd()
    $process.WaitForExit()
    if ($process.ExitCode -ne 0) { throw "SOPS decrypt failed with exit code $($process.ExitCode); secret-bearing stderr was suppressed." }
    return $stdout
}

function Assert-ObservabilityPayload {
    param([Parameter(Mandatory = $true)]$Payload)
    $names = @($Payload.PSObject.Properties.Name)
    $required = @("LOKI_URL", "LOKI_USERNAME", "GRAFANA_CLOUD_API_KEY")
    foreach ($name in $required) {
        if ($names -notcontains $name -or [string]::IsNullOrEmpty([string]$Payload.$name)) { throw "Decrypted observability bundle is missing required key $name." }
    }
    foreach ($name in $names) {
        if ($required -notcontains $name) { throw "Decrypted observability bundle contains unsupported key $name." }
        if ([string]$Payload.$name -match "[`r`n`0]") { throw "Decrypted observability bundle contains a multi-line value." }
    }
}

$setClipboard = Get-Command Set-Clipboard -ErrorAction SilentlyContinue
if (-not $setClipboard) { throw "Set-Clipboard is unavailable in this PowerShell environment." }

$sops = Resolve-SoloVpsTool -Name "sops"
$fullStateRoot = [System.IO.Path]::GetFullPath($StateRoot)
if (-not $PolicyPath) { $PolicyPath = Join-Path $fullStateRoot "sops\.sops.yaml" }
if (-not $EncryptedPath) { $EncryptedPath = Join-Path $fullStateRoot "secrets\observability.enc.yaml" }
$fullPolicyPath = [System.IO.Path]::GetFullPath($PolicyPath)
$fullEncryptedPath = [System.IO.Path]::GetFullPath($EncryptedPath)
$fullKeyPath = [System.IO.Path]::GetFullPath($KeyPath)
foreach ($path in @($fullPolicyPath, $fullEncryptedPath, $fullKeyPath)) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Required file is missing: $path" }
}

$json = Invoke-SopsDecrypt -Sops $sops -Policy $fullPolicyPath -Encrypted $fullEncryptedPath -Key $fullKeyPath
try { $payload = $json | ConvertFrom-Json } catch { throw "SOPS output is not valid JSON." }
Assert-ObservabilityPayload -Payload $payload
if ([string]$payload.LOKI_USERNAME -notmatch "^[0-9]+$") { throw "Grafana Cloud Logs user ID must be numeric." }
$tokenText = [string]$payload.GRAFANA_CLOUD_API_KEY
if ($tokenText -match "\s" -or $tokenText.Contains("#") -or $tokenText.Contains('"') -or $tokenText.Contains("'")) {
    throw "Grafana Cloud access-policy token contains characters that are unsafe in a Fluent Bit classic configuration value."
}

$lokiUri = $null
if (-not [Uri]::TryCreate([string]$payload.LOKI_URL, [UriKind]::Absolute, [ref]$lokiUri)) { throw "LOKI_URL is not a valid absolute URI." }
if ($lokiUri.Scheme -ne "https" -or $lokiUri.Port -ne 443 -or $lokiUri.AbsolutePath -ne "/loki/api/v1/push") {
    throw "LOKI_URL must be an HTTPS Grafana/Loki push URL on port 443 ending in /loki/api/v1/push."
}

$config = @"
[SERVICE]
    Flush             5
    Daemon            off
    Log_Level         info

[INPUT]
    Name              forward
    Listen            0.0.0.0
    Port              24224
    Buffer_Chunk_Size 1M
    Buffer_Max_Size   6M

[FILTER]
    Name              modify
    Match             *
    Rename            COOLIFY_APP_NAME service_name
    Rename            container_name container

[OUTPUT]
    Name        loki
    Match       *
    Host        $($lokiUri.Host)
    Port        443
    URI         /loki/api/v1/push
    TLS         On
    TLS.Verify  On
    HTTP_User   $($payload.LOKI_USERNAME)
    HTTP_Passwd $($payload.GRAFANA_CLOUD_API_KEY)
    Labels      job=solo-vps
    Label_Keys  `$service_name,`$source
    Line_Format json
"@

Set-Clipboard -Value $config
$payload = $null
$json = $null
$config = $null

Write-Host "PASS Grafana Cloud Custom FluentBit Configuration copied to clipboard"
Write-Host "  destination: Coolify Server > Configuration > Log Drains > Custom FluentBit Configuration"
Write-Host "  plaintext file created: no"
Write-Host "  token printed: no"
Write-Host "  Docker socket access required: no"
Write-Host "  next: paste into Coolify with Custom FluentBit still disabled, Save, then enable it"
Write-Host "  after paste: clear the clipboard with: Set-Clipboard -Value ''"
Write-Host "  if Windows Clipboard History/sync is enabled: clear that sensitive history entry too (Win+V -> Clear all)"
