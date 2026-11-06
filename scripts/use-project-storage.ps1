$ErrorActionPreference = 'Stop'
$eurekaRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$eurekaStorage = Join-Path $eurekaRoot 'orther'
foreach ($folder in @('tmp','cache/pip','cache/uv','cache/huggingface','cache/torch','cache/pycache','tools','python','models','logs','artifacts')) {
    $null = New-Item -ItemType Directory -Force -Path (Join-Path $eurekaStorage $folder)
}
$env:TEMP = Join-Path $eurekaStorage 'tmp'
$env:TMP = $env:TEMP
$env:TMPDIR = $env:TEMP
$env:PIP_CACHE_DIR = Join-Path $eurekaStorage 'cache/pip'
$env:UV_CACHE_DIR = Join-Path $eurekaStorage 'cache/uv'
$env:UV_INSTALL_DIR = Join-Path $eurekaStorage 'tools'
$env:UV_PYTHON_INSTALL_DIR = Join-Path $eurekaStorage 'python'
$env:XDG_CACHE_HOME = Join-Path $eurekaStorage 'cache'
$env:HF_HOME = Join-Path $eurekaStorage 'cache/huggingface'
$env:HF_HUB_CACHE = Join-Path $env:HF_HOME 'hub'
$env:HF_MODULES_CACHE = Join-Path $env:HF_HOME 'modules'
$env:TORCH_HOME = Join-Path $eurekaStorage 'cache/torch'
$env:CUDA_CACHE_PATH = Join-Path $eurekaStorage 'cache/cuda'
$env:TRITON_CACHE_DIR = Join-Path $eurekaStorage 'cache/triton'
$env:TORCH_EXTENSIONS_DIR = Join-Path $eurekaStorage 'cache/torch-extensions'
$env:TORCHINDUCTOR_CACHE_DIR = Join-Path $eurekaStorage 'cache/torchinductor'
$env:PLAYWRIGHT_BROWSERS_PATH = Join-Path $eurekaStorage 'cache/playwright'
$env:PYTHONPYCACHEPREFIX = Join-Path $eurekaStorage 'cache/pycache'
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'
$env:OLLAMA_MODELS = Join-Path $eurekaStorage 'models/ollama'
$env:TTS_OUTPUT_DIR = Join-Path $eurekaStorage 'audio'
# Process-scoped only: do not change Windows/global application configuration.
