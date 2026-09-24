[CmdletBinding()]
param(
    [string]$KeyPath = (Join-Path $env:USERPROFILE ".config\solo-vps\age-key.txt")
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

function Set-SoloVpsPrivateAcl {
    param([Parameter(Mandatory = $true)][string]$Path)

    $acl = Get-Acl -LiteralPath $Path
    $acl.SetAccessRuleProtection($true, $false)
    foreach ($rule in @($acl.Access)) {
        [void]$acl.RemoveAccessRuleSpecific($rule)
    }

    $currentUser = [System.Security.Principal.WindowsIdentity]::GetCurrent().User
    if ($null -eq $currentUser) {
        throw "Could not determine the current Windows user SID."
    }

    $system = [System.Security.Principal.SecurityIdentifier]::new("S-1-5-18")
    $administrators = [System.Security.Principal.SecurityIdentifier]::new("S-1-5-32-544")
    $rights = [System.Security.AccessControl.FileSystemRights]::FullControl
    $inheritance = if ((Get-Item -LiteralPath $Path).PSIsContainer) {
        [System.Security.AccessControl.InheritanceFlags]::ContainerInherit -bor [System.Security.AccessControl.InheritanceFlags]::ObjectInherit
    } else {
        [System.Security.AccessControl.InheritanceFlags]::None
    }
    $propagation = [System.Security.AccessControl.PropagationFlags]::None
    $allow = [System.Security.AccessControl.AccessControlType]::Allow

    foreach ($identity in @($currentUser, $system, $administrators)) {
        $rule = [System.Security.AccessControl.FileSystemAccessRule]::new(
            $identity,
            $rights,
            $inheritance,
            $propagation,
            $allow
        )
        [void]$acl.AddAccessRule($rule)
    }

    Set-Acl -LiteralPath $Path -AclObject $acl
}

function Invoke-AgeKeygenQuiet {
    param(
        [Parameter(Mandatory = $true)][string]$Executable,
        [Parameter(Mandatory = $true)][string[]]$Arguments
    )

    # Windows PowerShell can turn a native program's stderr into a terminating
    # NativeCommandError when ErrorActionPreference is Stop, even when the
    # program exits successfully. age-keygen writes informational output to
    # stderr, so capture only its exit code/stdout here.
    $previousPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        $stdout = @(& $Executable @Arguments 2>$null)
        $exitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $previousPreference
    }

    [pscustomobject]@{
        ExitCode = $exitCode
        Stdout = ($stdout | Out-String).Trim()
    }
}

function Get-AgeRecipient {
    param(
        [Parameter(Mandatory = $true)][string]$Executable,
        [Parameter(Mandatory = $true)][string]$Path
    )

    $result = Invoke-AgeKeygenQuiet -Executable $Executable -Arguments @("-y", $Path)
    if ($result.ExitCode -ne 0 -or $result.Stdout -notmatch '^age1[0-9a-z]+$') {
        throw "Could not derive a valid public age recipient from: $Path"
    }
    return $result.Stdout
}

$ageKeygen = Resolve-SoloVpsTool -Name "age-keygen"
$fullKeyPath = [System.IO.Path]::GetFullPath($KeyPath)
$keyDir = Split-Path -Parent $fullKeyPath

New-Item -ItemType Directory -Force -Path $keyDir | Out-Null
Set-SoloVpsPrivateAcl -Path $keyDir

if (Test-Path -LiteralPath $fullKeyPath) {
    if (-not (Test-Path -LiteralPath $fullKeyPath -PathType Leaf)) {
        throw "Age key path exists but is not a file: $fullKeyPath"
    }

    Set-SoloVpsPrivateAcl -Path $fullKeyPath
    $recipient = Get-AgeRecipient -Executable $ageKeygen -Path $fullKeyPath

    Write-Host "PASS Solo VPS age key already exists"
    Write-Host "  private key: $fullKeyPath"
    Write-Host "  public recipient: $recipient"
    Write-Host "  existing key replaced: no"
    Write-Host ""
    Write-Host "Next: .\scripts\windows\init-sops-policy.ps1"
    return
}

$result = Invoke-AgeKeygenQuiet -Executable $ageKeygen -Arguments @("-o", $fullKeyPath)
if ($result.ExitCode -ne 0 -or -not (Test-Path -LiteralPath $fullKeyPath -PathType Leaf)) {
    Remove-Item -LiteralPath $fullKeyPath -Force -ErrorAction SilentlyContinue
    throw "age-keygen.exe failed while creating the key."
}

Set-SoloVpsPrivateAcl -Path $fullKeyPath

try {
    $recipient = Get-AgeRecipient -Executable $ageKeygen -Path $fullKeyPath
}
catch {
    Remove-Item -LiteralPath $fullKeyPath -Force -ErrorAction SilentlyContinue
    throw
}

Write-Host "PASS Solo VPS age key created"
Write-Host "  private key: $fullKeyPath"
Write-Host "  public recipient: $recipient"
Write-Host "  private ACL: current user + SYSTEM + Administrators"
Write-Host ""
Write-Host "Keep the private file off Git/VPS and copy it once to a place you can recover from."
Write-Host "Next: .\scripts\windows\init-sops-policy.ps1"
