param([string]$Compiler = 'C:\Program Files (x86)\Inno Setup 6\ISCC.exe')
$ErrorActionPreference = 'Stop'
Push-Location (Split-Path $PSScriptRoot)
try {
    Push-Location frontend
    npm.cmd ci
    if ($LASTEXITCODE) { throw 'Frontend dependencies failed' }
    npx.cmd vite build --config vite.next.config.ts
    if ($LASTEXITCODE) { throw 'Frontend build failed' }
    Pop-Location
    python -m PyInstaller --noconfirm --clean --windowed --onedir --name TrainingViewer --paths src --add-data 'src/viewer_next/web;viewer_next/web' --add-data 'src/viewer_next/writer.py;viewer_next' --collect-all webview --hidden-import uvicorn.logging --hidden-import uvicorn.loops.auto --hidden-import uvicorn.protocols.http.auto --hidden-import uvicorn.protocols.websockets.auto --hidden-import uvicorn.lifespan.on desktop_entry.py
    if ($LASTEXITCODE) { throw 'Desktop build failed' }
    python tools/next_licenses.py
    if ($LASTEXITCODE) { throw 'License collection failed' }
    if (!(Test-Path -LiteralPath packaging/vendor/WebView2.exe)) { throw 'Place the Microsoft WebView2 x64 Evergreen offline installer at packaging/vendor/WebView2.exe' }
    & $Compiler packaging/next.iss
    if ($LASTEXITCODE) { throw 'Installer build failed' }
} finally { Pop-Location }
