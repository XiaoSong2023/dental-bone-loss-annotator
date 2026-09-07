[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$InstallDirectory,
    [Parameter(Mandatory=$true)][string]$ReportDirectory
)
$ErrorActionPreference = 'Stop'
$InstallDirectory = [IO.Path]::GetFullPath($InstallDirectory)
$ReportDirectory = [IO.Path]::GetFullPath($ReportDirectory)
New-Item -ItemType Directory -Path $ReportDirectory -Force | Out-Null
$guiPath = Join-Path $InstallDirectory '牙槽骨吸收测量AI.exe'
$workerPath = Join-Path $InstallDirectory 'runtime\PanoDentalWorker.exe'
$modelsPath = Join-Path $InstallDirectory 'models'
foreach ($path in @($guiPath, $workerPath)) {
    if (!(Test-Path -LiteralPath $path -PathType Leaf)) { throw "Missing packaged executable: $path" }
}
$savedEnvironment = @{}
foreach ($name in @('PATH', 'PYTHONHOME', 'PYTHONPATH', 'VIRTUAL_ENV', 'SELFTEST_QUIET', 'SELFTEST_OUT')) {
    $savedEnvironment[$name] = [Environment]::GetEnvironmentVariable($name, 'Process')
}
try {
    # Prove launch without discovering Python, the source venv, or source modules.
    $env:PATH = "$env:SystemRoot\System32;$env:SystemRoot"
    $env:PYTHONHOME = $null
    $env:PYTHONPATH = $null
    $env:VIRTUAL_ENV = $null
    $env:SELFTEST_QUIET = '1'
    $env:SELFTEST_OUT = Join-Path $ReportDirectory 'gui-selftest.log'
    $guiInfo = [Diagnostics.ProcessStartInfo]::new()
    $guiInfo.FileName = $guiPath
    $guiInfo.Arguments = '--selftest'
    $guiInfo.WorkingDirectory = $ReportDirectory
    $guiInfo.UseShellExecute = $false
    $gui = [Diagnostics.Process]::Start($guiInfo)
    if (!$gui.WaitForExit(90000)) { $gui.Kill(); throw 'Packaged GUI selftest timed out.' }
    if ($gui.ExitCode -ne 0) { throw "Packaged GUI exited with $($gui.ExitCode)." }
    $guiResult = Get-Content -LiteralPath $env:SELFTEST_OUT -Raw
    if (!$guiResult.Contains('[selftest] OK')) { throw 'Packaged GUI did not report success.' }

    $workerInfo = [Diagnostics.ProcessStartInfo]::new()
    $workerInfo.FileName = $workerPath
    $workerInfo.Arguments = '--selftest --models "' + $modelsPath + '"'
    $workerInfo.WorkingDirectory = $ReportDirectory
    $workerInfo.UseShellExecute = $false
    $workerInfo.CreateNoWindow = $true
    $workerInfo.RedirectStandardOutput = $true
    $workerInfo.RedirectStandardError = $true
    $worker = [Diagnostics.Process]::Start($workerInfo)
    $outputTask = $worker.StandardOutput.ReadToEndAsync()
    $errorTask = $worker.StandardError.ReadToEndAsync()
    if (!$worker.WaitForExit(180000)) { $worker.Kill(); throw 'Packaged worker selftest timed out.' }
    $workerOutput = $outputTask.GetAwaiter().GetResult()
    $workerErrors = $errorTask.GetAwaiter().GetResult()
    $workerOutput | Set-Content -LiteralPath (Join-Path $ReportDirectory 'worker-selftest.jsonl') -Encoding UTF8
    $workerErrors | Set-Content -LiteralPath (Join-Path $ReportDirectory 'worker-selftest.stderr.log') -Encoding UTF8
    if ($worker.ExitCode -ne 0) { throw "Packaged worker exited with $($worker.ExitCode): $workerErrors" }
    if ($workerOutput -notmatch '"frozen"\s*:\s*true') {
        throw 'Worker selftest did not confirm frozen runtime execution.'
    }
    [ordered]@{
        gui_executable = $guiPath
        worker_executable = $workerPath
        gui_exit_code = $gui.ExitCode
        worker_exit_code = $worker.ExitCode
        launch_directory = $ReportDirectory
        path_during_test = $env:PATH
        pythonhome_during_test = $env:PYTHONHOME
        pythonpath_during_test = $env:PYTHONPATH
        virtual_env_during_test = $env:VIRTUAL_ENV
        checked_at_utc = [DateTime]::UtcNow.ToString('o')
    } | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $ReportDirectory 'frozen-launch.json') -Encoding UTF8
    Write-Output $guiResult
    Write-Output $workerOutput
} finally {
    foreach ($name in $savedEnvironment.Keys) {
        [Environment]::SetEnvironmentVariable($name, $savedEnvironment[$name], 'Process')
    }
}
