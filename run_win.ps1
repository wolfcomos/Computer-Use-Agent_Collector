param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$CollectorArgs
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

$pythonCandidates = @(
    (Join-Path $ScriptDir ".venv\Scripts\python.exe"),
    (Join-Path $ScriptDir ".venv\bin\python3")
)

$Python = $null
foreach ($candidate in $pythonCandidates) {
    if (Test-Path $candidate) {
        $Python = $candidate
        break
    }
}

if (-not $Python) {
    $command = Get-Command python -ErrorAction SilentlyContinue
    if ($command) {
        $Python = $command.Source
    }
}

if (-not $Python) {
    $command = Get-Command py -ErrorAction SilentlyContinue
    if ($command) {
        $Python = $command.Source
        $CollectorArgs = @("-3") + $CollectorArgs
    }
}

if (-not $Python) {
    Write-Error "Python not found. Create a venv first: python -m venv .venv; .\.venv\Scripts\python.exe -m pip install -r requirements.txt"
    exit 1
}

$nativeModule = @(
    Get-ChildItem -Path (Join-Path $ScriptDir "build") -Filter "cua_capture*.pyd" -ErrorAction SilentlyContinue
    Get-ChildItem -Path (Join-Path $ScriptDir "build") -Recurse -Filter "cua_capture*.pyd" -ErrorAction SilentlyContinue
) | Select-Object -First 1

if (-not $env:CUA_CAPTURE_BACKEND) {
    if ($nativeModule) {
        $env:CUA_CAPTURE_BACKEND = "native"
    } else {
        $env:CUA_CAPTURE_BACKEND = "python"
        Write-Host "Native Windows cua_capture module not found; using Python backend."
        Write-Host "Build native support with:"
        Write-Host '  & "C:\Program Files\CMake\bin\cmake.exe" -S . -B build -DPython3_EXECUTABLE="$PWD\.venv\Scripts\python.exe"'
        Write-Host '  & "C:\Program Files\CMake\bin\cmake.exe" --build build --config Release'
    }
}

$env:CUA_SESSION_TYPE = "windows"

& $Python (Join-Path $ScriptDir "collector.py") @CollectorArgs
exit $LASTEXITCODE
