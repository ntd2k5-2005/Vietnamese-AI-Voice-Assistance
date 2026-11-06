$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
. (Join-Path $PSScriptRoot 'use-project-storage.ps1')
$Venvs = Join-Path $Root "orther/envs"
$Runtime = Get-Content (Join-Path $Root "services\tts\runtime.json") | ConvertFrom-Json
$Manifest = Get-Content (Join-Path $Root "config\model_manifest.json") | ConvertFrom-Json
$OllamaModel = if ($env:OLLAMA_MODEL) { $env:OLLAMA_MODEL } else { $Manifest.components.llm.model_id }
$VieNeuDir = Join-Path $Root "orther/runtime/VieNeu-TTS"

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Host "Installing uv..."
    powershell -ExecutionPolicy Bypass -Command "irm https://astral.sh/uv/install.ps1 | iex"
    $env:Path = "$env:UV_INSTALL_DIR;$env:Path"
}
$Uv = (Get-Command uv).Source
& $Uv python install 3.12
New-Item -ItemType Directory -Force -Path $Venvs | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $Root "orther/runtime") | Out-Null

foreach ($name in @("stt", "rag", "llm", "app")) {
    if (-not (Test-Path (Join-Path $Venvs "$name/Scripts/python.exe"))) {
        & $Uv venv --python 3.12 --seed (Join-Path $Venvs $name)
    }
}
& "$Venvs\stt\Scripts\python.exe" -m pip install -r "$Root\services\stt\requirements.txt" -r "$Root\services\stt\requirements-test.txt"
& "$Venvs\rag\Scripts\python.exe" -m pip install -e "$Root\services\rag[api,test,ui,ocr]"
& "$Venvs\llm\Scripts\python.exe" -m pip install -e "$Root\services\llm[api,test]"

if (-not (Test-Path (Join-Path $VieNeuDir ".git"))) {
    if (Test-Path $VieNeuDir) { throw "Thư mục VieNeu đã có dữ liệu nhưng chưa có Git. Kiểm tra trước: $VieNeuDir" }
    git clone $Runtime.repository $VieNeuDir
}
git -C $VieNeuDir fetch --depth 1 origin $Runtime.commit
git -C $VieNeuDir checkout --detach $Runtime.commit
$Actual = (git -C $VieNeuDir rev-parse HEAD).Trim()
if ($Actual -ne $Runtime.commit) { throw "VieNeu commit mismatch: expected=$($Runtime.commit) actual=$Actual" }
$TtsVenv = Join-Path $Venvs "tts"
if (Test-Path $TtsVenv) { throw "Môi trường TTS đã tồn tại. Giữ nguyên; hãy dùng môi trường đã cài hoặc lưu trữ nó trước khi cài lại." }
$env:UV_PROJECT_ENVIRONMENT = $TtsVenv
$env:UV_PYTHON = "3.12"
& $Uv sync --project $VieNeuDir --frozen
Remove-Item Env:UV_PROJECT_ENVIRONMENT
Remove-Item Env:UV_PYTHON
& $Uv pip install --python "$TtsVenv\Scripts\python.exe" "fastapi>=0.115,<1" "uvicorn[standard]>=0.30,<1" "pydantic>=2.8,<3" "pytest>=8,<10"

& "$Venvs\app\Scripts\python.exe" -m pip install -e "$Root\app[demo,dev]"

if (-not (Get-Command ollama -ErrorAction SilentlyContinue)) {
    throw "Ollama is required for the baseline LLM. Install Ollama, then rerun setup."
}
# A pre-existing global Ollama daemon does not inherit OLLAMA_MODELS here.
# Require the separately launched Eureka daemon; never pull into global C: storage.
if ($env:OLLAMA_HOST -ne '127.0.0.1:11436') {
    throw 'Mở terminal Eureka riêng, dot-source scripts/use-project-storage.ps1, đặt OLLAMA_HOST=127.0.0.1:11436 rồi chạy ollama serve. Sau đó đặt cùng OLLAMA_HOST trong terminal cài đặt và chạy lại.'
}
& ollama pull $OllamaModel
$Tags = Invoke-RestMethod -Uri "http://127.0.0.1:11436/api/tags"
$Installed = $Tags.models | Where-Object { $_.model -eq $OllamaModel -or $_.name -eq $OllamaModel } | Select-Object -First 1
if (-not $Installed) { throw "Ollama model missing after pull: $OllamaModel" }
$ExpectedDigest = $Manifest.components.llm.manifest_digest
if ($ExpectedDigest -and $Installed.digest -ne $ExpectedDigest) {
    throw "Ollama digest mismatch: expected=$ExpectedDigest actual=$($Installed.digest)"
}
Write-Host ""
Write-Host "V10 environments installed. VieNeu pinned at $($Runtime.commit)."
Write-Host "Run: $Venvs\app\Scripts\python.exe $Root\scripts\start_services.py --profile local-balanced --with-web"
