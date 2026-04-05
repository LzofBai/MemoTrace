# PowerShell script to install yara-python with Visual Studio Build Tools

# Find the Visual Studio installation path
$VSPath = "C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools"
$vcvarsPath = Join-Path $VSPath "VC\Auxiliary\Build\vcvarsall.bat"

if (-not (Test-Path $vcvarsPath)) {
    Write-Host "❌ Visual Studio Build Tools not found at $VSPath"
    exit 1
}

Write-Host "✅ Found Visual Studio Build Tools at $VSPath"
Write-Host "🔧 Configuring C++ compiler environment..."

# Create a temporary batch file to set up the environment and run pip
$tempBat = [System.IO.Path]::GetTempFileName() + ".bat"
$pythonExe = "C:\Python314\python.exe"

@"
@echo off
REM Set up Visual Studio build environment
call "$vcvarsPath" x64

REM Install yara-python
echo.
echo 🚀 Starting yara-python installation...
echo.
"$pythonExe" -m pip install yara-python --no-cache-dir

REM Check if installation was successful
"$pythonExe" -c "import yara; print('✅ yara-python installed successfully!')" 2>nul
if %ERRORLEVEL% equ 0 (
    echo.
    echo ✅ Installation completed successfully!
) else (
    echo.
    echo ❌ Installation may have failed. Please check the output above.
)
"@ | Out-File -FilePath $tempBat -Encoding ASCII

Write-Host "Running installation script..."
& cmd /c $tempBat

# Clean up
Remove-Item $tempBat -Force -ErrorAction SilentlyContinue

Write-Host ""
Write-Host "Installation complete!"
