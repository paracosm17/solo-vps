[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$VpsHost,
    [Parameter(Mandatory = $true)][string]$VpsUser,
    [string]$RemoteProject = "~/solo-vps",
    [string]$IdentityFile = "",
    [string]$KeyPath = (Join-Path $env:USERPROFILE ".config\solo-vps\age-key.txt"),
    [string]$StateRoot = (Join-Path $env:LOCALAPPDATA "solo-vps\state"),
    [string]$PolicyPath = "",
    [string]$EncryptedPath = ""
)

$ErrorActionPreference = "Stop"

if ($VpsUser -notmatch '^[a-z_][a-z0-9_-]{0,31}$') { throw "VpsUser must be a simple Linux username." }
if ([string]::IsNullOrWhiteSpace($VpsHost) -or $VpsHost.StartsWith('-') -or $VpsHost -match '\s') { throw "VpsHost is invalid." }
if ($RemoteProject -notmatch '^[A-Za-z0-9_./~+-]+$') { throw "RemoteProject contains unsupported shell characters." }

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
        "decrypt", "--input-type", "yaml", "--output-type", "json",
        (Quote-ProcessArgument $Encrypted)
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

function Assert-MetricsPayload {
    param([Parameter(Mandatory = $true)]$Payload)
    $names = @($Payload.PSObject.Properties.Name)
    $required = @("PROMETHEUS_URL", "PROMETHEUS_USERNAME", "GRAFANA_CLOUD_METRICS_API_KEY")
    foreach ($name in $required) {
        if ($names -notcontains $name -or [string]::IsNullOrEmpty([string]$Payload.$name)) { throw "Decrypted metrics bundle is missing required key $name." }
    }
    foreach ($name in $names) {
        if ($required -notcontains $name) { throw "Decrypted metrics bundle contains unsupported key $name." }
        if ([string]$Payload.$name -match "[`r`n`0]") { throw "Decrypted metrics bundle contains a multi-line value." }
    }
    $uri = $null
    if (-not [Uri]::TryCreate([string]$Payload.PROMETHEUS_URL, [UriKind]::Absolute, [ref]$uri) -or $uri.Scheme -ne "https" -or -not $uri.AbsolutePath.TrimEnd("/").EndsWith("/api/prom/push")) { throw "Decrypted PROMETHEUS_URL is invalid." }
    if ([string]$Payload.PROMETHEUS_USERNAME -notmatch '^[0-9]+$') { throw "Decrypted PROMETHEUS_USERNAME must be numeric." }
}

$sops = Resolve-SoloVpsTool -Name "sops"
$sshCommand = Get-Command "ssh.exe" -ErrorAction SilentlyContinue
if (-not $sshCommand) { throw "ssh.exe is unavailable. Install/enable the Windows OpenSSH Client first." }
$fullStateRoot = [System.IO.Path]::GetFullPath($StateRoot)
if (-not $PolicyPath) { $PolicyPath = Join-Path $fullStateRoot "sops\.sops.yaml" }
if (-not $EncryptedPath) { $EncryptedPath = Join-Path $fullStateRoot "secrets\metrics.enc.yaml" }
$fullPolicyPath = [System.IO.Path]::GetFullPath($PolicyPath)
$fullEncryptedPath = [System.IO.Path]::GetFullPath($EncryptedPath)
$fullKeyPath = [System.IO.Path]::GetFullPath($KeyPath)
foreach ($path in @($fullPolicyPath, $fullEncryptedPath, $fullKeyPath)) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Required file is missing: $path" }
}

$json = Invoke-SopsDecrypt -Sops $sops -Policy $fullPolicyPath -Encrypted $fullEncryptedPath -Key $fullKeyPath
try { $payload = $json | ConvertFrom-Json } catch { throw "SOPS output is not valid JSON." }
Assert-MetricsPayload -Payload $payload
$payload = $null

$remoteCommand = "cd $RemoteProject && sudo -n python3 scripts/install_metrics_credentials.py apply"
$sshArgs = @("-T", "-o", "BatchMode=yes")
if ($IdentityFile) {
    $fullIdentity = [System.IO.Path]::GetFullPath($IdentityFile)
    if (-not (Test-Path -LiteralPath $fullIdentity -PathType Leaf)) { throw "SSH identity file is missing: $fullIdentity" }
    $sshArgs += @("-i", $fullIdentity)
}
$sshArgs += @("$VpsUser@$VpsHost", $remoteCommand)
$quotedArgs = ($sshArgs | ForEach-Object { Quote-ProcessArgument ([string]$_) }) -join " "

$psi = New-Object System.Diagnostics.ProcessStartInfo
$psi.FileName = $sshCommand.Source
$psi.Arguments = $quotedArgs
$psi.UseShellExecute = $false
$psi.RedirectStandardInput = $true
$psi.RedirectStandardOutput = $true
$psi.RedirectStandardError = $true
$psi.CreateNoWindow = $true
$process = New-Object System.Diagnostics.Process
$process.StartInfo = $psi
if (-not $process.Start()) { throw "Could not start ssh.exe" }
$process.StandardInput.Write($json)
$process.StandardInput.Close()
$json = $null
$stdout = $process.StandardOutput.ReadToEnd()
$stderr = $process.StandardError.ReadToEnd()
$process.WaitForExit()
if ($process.ExitCode -ne 0) {
    $detail = ($stderr -split "`r?`n" | Where-Object { $_ } | Select-Object -Last 1)
    if ($detail) { throw "VPS metrics credential installation failed: $detail" }
    throw "VPS metrics credential installation failed with exit code $($process.ExitCode)."
}
if ($stdout) { Write-Host $stdout.TrimEnd() }
Write-Host "PASS workstation-to-VPS metrics credential delivery"
Write-Host "  transport: SSH stdin"
Write-Host "  age private key copied to VPS: no"
Write-Host "  plaintext stored in source checkout: no"
Write-Host "  telemetry sent: no"
