[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$InstallDirectory,
    [Parameter(Mandatory=$true)][string]$ReportDirectory
)
$ErrorActionPreference = 'Stop'
$InstallDirectory = [IO.Path]::GetFullPath($InstallDirectory)
$ReportDirectory = [IO.Path]::GetFullPath($ReportDirectory)
$expectedExe = Join-Path $InstallDirectory '牙槽骨吸收测量AI.exe'
if (!(Test-Path -LiteralPath $expectedExe -PathType Leaf)) { throw 'Installed shared GUI executable is missing.' }
New-Item -ItemType Directory -Path $ReportDirectory -Force | Out-Null
$shellObject = New-Object -ComObject WScript.Shell
$locations = @(
    [Environment]::GetFolderPath('DesktopDirectory'),
    (Join-Path ([Environment]::GetFolderPath('Programs')) '牙槽骨吸收测量')
)
$results = @()
foreach ($location in $locations) {
    $path = Join-Path $location '牙槽骨吸收测量.lnk'
    if (!(Test-Path -LiteralPath $path -PathType Leaf)) { throw "Missing unified shortcut: $path" }
    # Opening an existing shortcut is read-only; do not call Save().
    $shortcut = $shellObject.CreateShortcut($path)
    if ($shortcut.TargetPath -ne $expectedExe -or ![string]::IsNullOrWhiteSpace($shortcut.Arguments)) {
        throw "Shortcut does not select the unified executable without mode arguments: $path"
    }
    $results += [ordered]@{ path = $path; target = $shortcut.TargetPath;
        arguments = $shortcut.Arguments; workflow = 'unified' }
}
$legacy = @()
foreach ($location in @([Environment]::GetFolderPath('DesktopDirectory'),
    (Join-Path ([Environment]::GetFolderPath('Programs')) '牙槽骨吸收测量AI'))) {
    foreach ($name in @('牙槽骨吸收测量AI', '牙槽骨吸收测量（分割人工版）')) {
        $legacy += Join-Path $location ($name + '.lnk')
    }
}
$legacy += Join-Path ([Environment]::GetFolderPath('Programs')) '牙槽骨吸收测量AI\卸载 牙槽骨吸收测量AI.lnk'
$leftovers = @($legacy | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf })
if ($leftovers.Count) { throw "Obsolete shortcuts remain: $($leftovers -join ', ')" }
[ordered]@{ status = 'passed'; shared_executable = $expectedExe; shortcuts = $results;
    obsolete_shortcuts_present = $leftovers;
    checked_at_utc = [DateTime]::UtcNow.ToString('o') } |
    ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $ReportDirectory 'shortcuts.json') -Encoding UTF8
Get-Content -LiteralPath (Join-Path $ReportDirectory 'shortcuts.json')
