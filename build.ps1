# Builds installer_output\LeadFinder-Setup.exe:
#   official signed Python embeddable runtime + PyPI wheels + app source -> Inno Setup.
$ErrorActionPreference = "Stop"
$root  = $PSScriptRoot
$pyVer = "3.12.10"
$stage = Join-Path $root "build_embed"
$cache = Join-Path $root "build_cache"
$zip   = Join-Path $cache "python-$pyVer-embed-amd64.zip"

New-Item -ItemType Directory -Force $cache | Out-Null
if (-not (Test-Path $zip)) {
    Write-Host "Downloading Python $pyVer embeddable runtime..."
    Invoke-WebRequest "https://www.python.org/ftp/python/$pyVer/python-$pyVer-embed-amd64.zip" -OutFile $zip -UseBasicParsing
}
if (Test-Path $stage) { Remove-Item -Recurse -Force $stage }
$rt  = Join-Path $stage "runtime"
$app = Join-Path $stage "app"
Expand-Archive $zip $rt

# site-packages + the app folder on sys.path, and enable site
$pth = @("python312.zip", ".", "Lib\site-packages", "..\app", "import site") -join "`r`n"
[IO.File]::WriteAllText((Join-Path $rt "python312._pth"), $pth + "`r`n")

Write-Host "Installing dependencies (binary wheels only)..."
python -m pip install --disable-pip-version-check --no-cache-dir --only-binary=:all: `
    --platform win_amd64 --python-version 3.12 --implementation cp `
    --target (Join-Path $rt "Lib\site-packages") -r (Join-Path $root "requirements.txt")
if ($LASTEXITCODE -ne 0) { throw "pip install failed" }

New-Item -ItemType Directory -Force $app | Out-Null
Copy-Item (Join-Path $root "*.py") $app

# DuckDB reads Overture / Foursquare from the cloud through its httpfs extension —
# ship it inside the app so nothing is downloaded (or blocked) at run time
$helper = Join-Path $cache "bundle_ext.py"
Set-Content $helper -Encoding ascii -Value @(
    "import sys, duckdb",
    "c = duckdb.connect()",
    "c.execute(""SET extension_directory='"" + sys.argv[1].replace(chr(92), '/') + ""'"")",
    "c.execute('INSTALL httpfs')",
    "print('httpfs bundled')")
& (Join-Path $rt "python.exe") $helper (Join-Path $app "duckdb_ext")
if ($LASTEXITCODE -ne 0) { throw "could not bundle the DuckDB httpfs extension" }
Copy-Item (Join-Path $root "leadfinder.ico") $app
Copy-Item -Recurse (Join-Path $root "static") (Join-Path $app "static")
New-Item -ItemType File (Join-Path $app ".installed") | Out-Null   # data goes to %LOCALAPPDATA%\Lead Finder
Get-ChildItem $stage -Recurse -Directory -Filter "__pycache__" | Remove-Item -Recurse -Force

$iscc = Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6\ISCC.exe"
if (-not (Test-Path $iscc)) { $iscc = "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe" }
& $iscc (Join-Path $root "installer.iss")
if ($LASTEXITCODE -ne 0) { throw "ISCC failed" }
Get-Item (Join-Path $root "installer_output\LeadFinder-Setup.exe") | Select-Object FullName, Length
