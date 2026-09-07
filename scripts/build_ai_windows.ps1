[CmdletBinding()]
param(
    [string]$WorkerProject = '',
    [string]$Version = '1.1.0-ai-preview',
    [ValidateSet('All', 'Gui', 'Worker', 'Assemble', 'Installer')]
    [string]$Stage = 'All'
)
$ErrorActionPreference = 'Stop'
$taskRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
if (!$WorkerProject) {
    $WorkerProject = Join-Path (Split-Path $taskRoot -Parent) '0907牙周全景片分割及标注系统开发\panodental'
}
$WorkerProject = [IO.Path]::GetFullPath($WorkerProject)
$guiPython = Join-Path $taskRoot '.venv\Scripts\python.exe'
$workerPython = Join-Path $WorkerProject '.venv\Scripts\python.exe'
$aiDist = Join-Path $taskRoot 'dist\AI-integrated'
$aiWork = Join-Path $taskRoot 'build\AI-integrated'
$bundle = Join-Path $aiDist 'PanoDentalAI'

function Invoke-Native([string]$Program, [string[]]$Arguments) {
    & $Program @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$Program exited with $LASTEXITCODE" }
}
function Require-File([string]$Path) {
    if (!(Test-Path -LiteralPath $Path -PathType Leaf)) { throw "Missing file: $Path" }
}
foreach ($folder in @($aiDist, $aiWork)) {
    New-Item -ItemType Directory -Path $folder -Force | Out-Null
}
$savedSource = $env:PANODENTAL_SOURCE
$savedVersion = $env:APP_VERSION
$savedPythonUtf8 = $env:PYTHONUTF8
$savedPath = $env:PATH
$savedPythonPath = $env:PYTHONPATH
$savedPythonHome = $env:PYTHONHOME
try {
    $env:PANODENTAL_SOURCE = Join-Path $WorkerProject 'src'
    $env:APP_VERSION = $Version
    $env:PYTHONUTF8 = '1'
    # Build with the same clean DLL search surface used for installed validation.
    # Host tools such as poppler/libheif ship incompatible ICU/UCRT DLLs on PATH.
    $env:PATH = "$env:SystemRoot\System32;$env:SystemRoot"
    $env:PYTHONPATH = $null
    $env:PYTHONHOME = $null
    if ($Stage -in @('All', 'Gui')) {
        Require-File $guiPython
        Invoke-Native $guiPython @('-m', 'PyInstaller', (Join-Path $taskRoot 'packaging\ai_gui.spec'),
            '--noconfirm', '--clean', '--distpath', $aiDist, '--workpath', (Join-Path $aiWork 'gui'))
    }
    if ($Stage -in @('All', 'Worker')) {
        Require-File $workerPython
        Require-File (Join-Path $taskRoot 'app\ai_worker.py')
        Invoke-Native $workerPython @('-m', 'PyInstaller', (Join-Path $taskRoot 'packaging\ai_worker.spec'),
            '--noconfirm', '--clean', '--distpath', (Join-Path $aiDist 'worker-build'),
            '--workpath', (Join-Path $aiWork 'worker'))
    }
    if ($Stage -in @('All', 'Assemble')) {
        Require-File (Join-Path $bundle '牙槽骨吸收测量AI.exe')
        $builtRuntime = Join-Path $aiDist 'worker-build\runtime'
        Require-File (Join-Path $builtRuntime 'PanoDentalWorker.exe')
        $runtimeTarget = Join-Path $bundle 'runtime'
        New-Item -ItemType Directory -Path $runtimeTarget -Force | Out-Null
        Get-ChildItem -LiteralPath $builtRuntime -Force | Copy-Item -Destination $runtimeTarget -Recurse -Force
        foreach ($relative in @('chocodo--teeth-segmentation-odontoai\best.pth',
                                'rummanadib023--denpar-bone-loss-v2\surf_pose.onnx')) {
            $source = Join-Path (Join-Path $taskRoot 'models') $relative
            Require-File $source
            $target = Join-Path (Join-Path $bundle 'models') $relative
            New-Item -ItemType Directory -Path (Split-Path $target -Parent) -Force | Out-Null
            Copy-Item -LiteralPath $source -Destination $target -Force
        }
        $notice = Join-Path $taskRoot 'models\README.md'
        Require-File $notice
        Copy-Item -LiteralPath $notice -Destination (Join-Path $bundle 'models\README.md') -Force
        $distributionExtras = Join-Path $taskRoot 'packaging\distribution'
        if (Test-Path -LiteralPath $distributionExtras -PathType Container) {
            Get-ChildItem -LiteralPath $distributionExtras -Force |
                Copy-Item -Destination $bundle -Recurse -Force
        }
        $licenseCollector = Join-Path $taskRoot 'packaging\collect_licenses.py'
        Invoke-Native $guiPython @($licenseCollector, '--output', (Join-Path $bundle 'THIRD_PARTY\gui'),
            'PySide6-Essentials', 'shiboken6', 'numpy', 'opencv-python-headless', 'openpyxl', 'et-xmlfile', 'pyinstaller')
        Invoke-Native $workerPython @($licenseCollector, '--output', (Join-Path $bundle 'THIRD_PARTY\worker'),
            'torch', 'torchvision', 'onnxruntime', 'numpy', 'pillow', 'pydantic', 'pydantic-core',
            'opencv-python-headless', 'sympy', 'networkx', 'Jinja2', 'MarkupSafe', 'filelock',
            'fsspec', 'typing-extensions', 'mpmath', 'coloredlogs', 'humanfriendly', 'flatbuffers', 'pyinstaller')
        Get-ChildItem -LiteralPath (Join-Path $taskRoot 'packaging\licenses') -Force |
            Copy-Item -Destination (Join-Path $bundle 'THIRD_PARTY') -Recurse -Force
        $assets = Get-ChildItem -LiteralPath $bundle -File -Recurse | ForEach-Object {
            [ordered]@{ path = $_.FullName.Substring($bundle.Length + 1).Replace('\', '/');
                bytes = $_.Length; sha256 = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLower() }
        }
        [ordered]@{ version = $Version; platform = 'windows-x64'; device = 'cpu';
            built_at_utc = [DateTime]::UtcNow.ToString('o'); files = @($assets) } |
            ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $aiDist 'bundle-manifest.json') -Encoding UTF8
    }
    if ($Stage -in @('All', 'Installer')) {
        Require-File (Join-Path $bundle 'runtime\PanoDentalWorker.exe')
        Require-File (Join-Path $bundle 'models\chocodo--teeth-segmentation-odontoai\best.pth')
        Require-File (Join-Path $bundle 'models\rummanadib023--denpar-bone-loss-v2\surf_pose.onnx')
        $isccPaths = @("$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe",
            "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe", "$env:ProgramFiles\Inno Setup 6\ISCC.exe")
        $iscc = $isccPaths | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
        if (!$iscc) { throw 'Inno Setup 6 ISCC.exe was not found; no installer was generated.' }
        Invoke-Native $iscc @((Join-Path $taskRoot 'installer_ai.iss'))
        $installer = Join-Path $aiDist "牙槽骨吸收测量AI_安装包_v$Version.exe"
        Require-File $installer
        Get-FileHash -LiteralPath $installer -Algorithm SHA256 |
            Select-Object Path, Hash | ConvertTo-Json |
            Set-Content -LiteralPath (Join-Path $aiDist 'installer-sha256.json') -Encoding UTF8
    }
} finally {
    $env:PANODENTAL_SOURCE = $savedSource
    $env:APP_VERSION = $savedVersion
    $env:PYTHONUTF8 = $savedPythonUtf8
    $env:PATH = $savedPath
    $env:PYTHONPATH = $savedPythonPath
    $env:PYTHONHOME = $savedPythonHome
}
