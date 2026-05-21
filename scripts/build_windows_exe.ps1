param(
    [string]$Name = "usage",
    [string]$UvPath = "uv"
)

$ErrorActionPreference = "Stop"

if ($env:OS -ne "Windows_NT") {
    throw "Windows exe packaging must run on Windows."
}

$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

$Uv = Get-Command $UvPath -ErrorAction SilentlyContinue
if ($null -eq $Uv) {
    throw "uv is required to build the exe. Install uv or pass -UvPath C:\path\to\uv.exe."
}

& $Uv.Source sync --frozen --group build

& $Uv.Source run pyinstaller `
    --noconfirm `
    --clean `
    --onefile `
    --windowed `
    --name $Name `
    --hidden-import "pystray" `
    --hidden-import "pystray._win32" `
    --hidden-import "PIL.Image" `
    --hidden-import "PIL.ImageDraw" `
    --add-data "assets;assets" `
    --add-data "usage_statusline.py;." `
    main.py

Write-Host "Built dist\$Name.exe"
