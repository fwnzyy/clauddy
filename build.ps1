# Builds dist\Clauddy.exe (one file, no console window).
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
python -m PyInstaller --noconfirm --onefile --noconsole --name Clauddy `
    --icon "$PSScriptRoot\pet.ico" --paths "$PSScriptRoot" `
    --hidden-import pystray._win32 --hidden-import panel --hidden-import media --hidden-import picker --hidden-import i18n `
    --collect-all winrt `
    --distpath dist --workpath build --specpath build `
    clauddy.py
Write-Host "Done: $PSScriptRoot\dist\Clauddy.exe"

