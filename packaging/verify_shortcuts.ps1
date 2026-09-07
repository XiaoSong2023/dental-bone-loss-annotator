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
    (Join-Path ([Environment]::GetFolderPath('Programs')) '牙槽骨吸收测量AI')
)
$entries = @(
    @{ name = '牙槽骨吸收测量AI'; mode = 'full' },
    @{ name = '牙槽骨吸收测量（分割人工版）'; mode = 'manual' }
)
$results = @()
foreach ($location in $locations) {
    foreach ($entry in $entries) {
        $path = Join-Path $location ($entry.name + '.lnk')
        if (!(Test-Path -LiteralPath $path -PathType Leaf)) { throw "Missing mode shortcut: $path" }
        # Opening an existing shortcut is read-only; do not call Save().
        $shortcut = $shellObject.CreateShortcut($path)
        $expectedArguments = '--annotation-mode ' + $entry.mode
        if ($shortcut.TargetPath -ne $expectedExe -or $shortcut.Arguments -ne $expectedArguments) {
            throw "Shortcut does not select the expected shared executable and mode: $path"
        }
        $results += [ordered]@{ path = $path; target = $shortcut.TargetPath;
            arguments = $shortcut.Arguments; mode = $entry.mode }
    }
}
[ordered]@{ status = 'passed'; shared_executable = $expectedExe; shortcuts = $results;
    checked_at_utc = [DateTime]::UtcNow.ToString('o') } |
    ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $ReportDirectory 'shortcuts.json') -Encoding UTF8
Get-Content -LiteralPath (Join-Path $ReportDirectory 'shortcuts.json')
