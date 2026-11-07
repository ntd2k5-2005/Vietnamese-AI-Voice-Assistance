"""Portable Colab/Kaggle launcher embedded verbatim in the standalone notebook.

No execution at import. Reuses the repository's service launcher and model
manifest; never creates smoke documents or implements a second voice pipeline.
"""
from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import shutil
import signal
import socket
import subprocess
import tarfile
import time
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path


REPOSITORY = "https://github.com/ntd2k5-2005/Vietnamese-AI-Voice-Assistance.git"
SOURCE_REVISION = "main"  # Generated notebooks pass an immutable app commit explicitly.
OLLAMA_PIN = {
    "model_id": "qwen3.5:4b",
    "previous_digest": "2a654d98e6fba55d452b7043684e9b57a947e393bbffa62485a7aac05ee4eefd",
    "manifest_digest": "d8b0f5e9760cd1682034f292d7ef72ec46f432149be0df7574bf2d6e92e38c04",
    "registry_url": "https://registry.ollama.ai/v2/library/qwen3.5/manifests/4b",
    "config_digest": "788a4d94bc3f431ac0cd067005be4b838a09330427962952420b05d10ecf84db",
    "family": "qwen35", "parameter_size": "4.2B", "quantization_level": "Q4_K_M",
    "checked_at": "2026-11-07",
}
ASSETS = {
    "uv": ("https://github.com/astral-sh/uv/releases/download/0.13.7/uv-x86_64-unknown-linux-gnu.tar.gz",
           "c5221ff41b7892bfc223543883600125f6a47fe845093e0f5bdff4f359196d83"),
    "ollama": ("https://github.com/ollama/ollama/releases/download/v0.32.15/ollama-linux-amd64.tar.zst",
               "50539c5fe9bf85887733355098dcdb266b433cb8c73fa180713417e9ed6e42bb"),
    "cloudflared": ("https://github.com/cloudflare/cloudflared/releases/download/2026.10.7/cloudflared-linux-amd64",
                    "1f99fb518b83dec2ba8d870a7cc991d82a77e6196295a3d2754ba17ab9f91872"),
}


def file_sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def find_tunnel_url(log):
    for value in reversed(re.findall(r"https://[a-z0-9][a-z0-9-]*\.trycloudflare\.com(?![a-zA-Z0-9.:-])", log)):
        if value.split("//")[1].split(".")[0] not in {"api", "www"}:
            return value
    return None


def choose_cuda_index(gpu_description):
    # Pascal/P100 is not supported by CUDA 12.8 PyTorch wheels. cu126 also
    # supports T4/A100; Blackwell needs the newer CUDA distribution.
    return "cu128" if re.search(r"(?:RTX\s*50|B100|B200|GB200|Blackwell)", gpu_description, re.I) else "cu126"


def require_ready(payload):
    # The gateway returns HTTP 200 even when an upstream is not ready.
    if payload.get("ready") is not True:
        failed = [name for name, status in payload.get("services", {}).items()
                  if status.get("ready") is not True or not status.get("reachable")]
        raise RuntimeError("Dịch vụ chưa sẵn sàng: " + ", ".join(failed or ["gateway"]) + ". Xem orther/logs.")




def normalized_digest(value):
    value = str(value or "").strip().lower().removeprefix("sha256:")
    if not re.fullmatch(r"[0-9a-f]{64}", value):
        raise ValueError(f"Digest SHA-256 không hợp lệ: {value!r}")
    return value


def listed_model(rows, name):
    return next((row for row in rows if row.get("name") == name or row.get("model") == name), None)


def model_matches(row, digest):
    try:
        return row is not None and normalized_digest(row.get("digest")) == normalized_digest(digest)
    except ValueError:
        return False




class CloudDemo:
    def __init__(self, *, revision=SOURCE_REVISION, gpu_for_asr_rag=False, cuda_index="auto"):
        if platform.system() != "Linux":
            raise RuntimeError("Notebook này chạy trên Colab/Kaggle Linux; không chạy cài đặt trên Windows.")
        if platform.machine() not in {"x86_64", "amd64"}:
            raise RuntimeError("Bản công cụ này cần máy Linux x86_64.")
        if Path("/kaggle/working").is_dir():
            self.platform = "Kaggle"
            base = Path("/kaggle/working")
        elif Path("/content").is_dir():
            self.platform = "Colab"
            base = Path("/content")
        else:
            raise RuntimeError("Không tìm thấy /content hoặc /kaggle/working. Hãy mở notebook trên Colab/Kaggle.")
        self.root = base / "Vietnamese-AI-Voice-Assistance"
        self.storage = self.root / "orther"
        self.revision = revision
        self.gpu_for_asr_rag = bool(gpu_for_asr_rag)
        self.cuda_index = cuda_index
        self.profile = "notebook-demo"
        self.env = dict(os.environ)
        self.processes = {}
        self.state = {}

    def save(self):
        path = self.storage / "runtime/notebook-state.json"
        temp = path.with_suffix(".tmp")
        temp.write_text(json.dumps(self.state, ensure_ascii=False, indent=2), encoding="utf-8")
        temp.replace(path)

    def tail(self, name, count=18):
        path = self.storage / "logs" / name
        return "\n".join(path.read_text(encoding="utf-8", errors="replace").splitlines()[-count:]) if path.exists() else "Chưa có log."

    def run(self, argv, *, cwd=None, label="setup", timeout=7200, quiet=False):
        argv = list(map(str, argv))
        log = self.storage / "logs" / (label + ".log")
        with log.open("ab") as output:
            process = subprocess.Popen(argv, cwd=cwd or self.root, env=self.env,
                                       stdout=output, stderr=subprocess.STDOUT, start_new_session=True)
            started = time.monotonic()
            notified = started
            try:
                while process.poll() is None:
                    if time.monotonic() - started > timeout:
                        raise TimeoutError(f"{label} quá hạn; xem {log}")
                    if not quiet and time.monotonic() - notified > 25:
                        print(f"  {label}: đang chạy ({int(time.monotonic()-started)} giây). Log: {log.name}", flush=True)
                        notified = time.monotonic()
                    time.sleep(.4)
                if process.returncode:
                    raise RuntimeError(f"{label} thất bại (mã {process.returncode}).\n{self.tail(log.name, 28)}")
            finally:
                if process.poll() is None:
                    os.killpg(process.pid, signal.SIGTERM)
                    try:
                        process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        os.killpg(process.pid, signal.SIGKILL)
                        process.wait()

    def prepare(self):
        if not shutil.which("git") or not shutil.which("nvidia-smi"):
            raise RuntimeError("Cần bật GPU và dùng image Colab/Kaggle có git, nvidia-smi.")
        gpu = subprocess.check_output(["nvidia-smi", "--query-gpu=name,memory.total,driver_version", "--format=csv,noheader"], text=True).strip()
        if not gpu:
            raise RuntimeError("Chưa có GPU. Bật GPU trong cài đặt notebook trước Run all.")
        if self.cuda_index == "auto":
            self.cuda_index = choose_cuda_index(gpu)
        if self.cuda_index not in {"cu126", "cu128"}:
            raise ValueError("CUDA_INDEX chỉ nhận auto, cu126 hoặc cu128.")
        free = shutil.disk_usage(self.root.parent).free / 1024**3
        if free < 10:
            raise RuntimeError(f"Ổ làm việc còn {free:.1f} GB; cần giải phóng dung lượng trước khi tải model.")
        print(f"{self.platform} | GPU: {gpu}\nỔ làm việc còn {free:.1f} GB | CUDA wheel: {self.cuda_index}")
        try:
            with urllib.request.urlopen("https://github.com/ntd2k5-2005/Vietnamese-AI-Voice-Assistance", timeout=20) as response:
                response.read(1)
        except Exception as error:
            raise RuntimeError("Không truy cập được GitHub. Với Kaggle, bật Internet trong Settings và kiểm tra tài khoản.") from error
        if not (self.root / ".git").exists():
            if self.root.exists():
                raise RuntimeError(f"Thư mục {self.root} có sẵn nhưng không phải repo; không ghi đè.")
            subprocess.run(["git", "clone", "--depth", "1", REPOSITORY, str(self.root)], check=True)
        for folder in ("tmp", "tools", "runtime", "logs", "envs", "downloads", "cache", "models"):
            (self.storage / folder).mkdir(parents=True, exist_ok=True)
        state_file = self.storage / "runtime/notebook-state.json"
        if state_file.exists():
            self.state = json.loads(state_file.read_text())
        self.state.setdefault("run_id", uuid.uuid4().hex)
        self.state.setdefault("processes", {})
        self.state.setdefault("stages", {})
        self.env.update({
            "TEMP": str(self.storage / "tmp"), "TMP": str(self.storage / "tmp"), "TMPDIR": str(self.storage / "tmp"),
            "UV_CACHE_DIR": str(self.storage / "cache/uv"), "UV_PYTHON_INSTALL_DIR": str(self.storage / "python"),
            "UV_PYTHON_BIN_DIR": str(self.storage / "tools"), "UV_TOOL_DIR": str(self.storage / "tools/uv-tools"),
            "UV_TOOL_BIN_DIR": str(self.storage / "tools"),
            "UV_LINK_MODE": "hardlink", "PIP_CACHE_DIR": str(self.storage / "cache/pip"),
            "HF_HOME": str(self.storage / "cache/huggingface"), "HF_HUB_CACHE": str(self.storage / "cache/huggingface/hub"),
            "HF_MODULES_CACHE": str(self.storage / "cache/huggingface/modules"), "TORCH_HOME": str(self.storage / "cache/torch"),
            "XDG_CACHE_HOME": str(self.storage / "cache"), "CUDA_CACHE_PATH": str(self.storage / "cache/cuda"),
            "TRITON_CACHE_DIR": str(self.storage / "cache/triton"), "TORCH_EXTENSIONS_DIR": str(self.storage / "cache/torch-extensions"),
            "PYTHONPYCACHEPREFIX": str(self.storage / "cache/pycache"), "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8",
            "OLLAMA_HOST": "127.0.0.1:11436", "OLLAMA_MODELS": str(self.storage / "models/ollama"),
            "OLLAMA_NUM_PARALLEL": "1", "OLLAMA_MAX_LOADED_MODELS": "1", "OLLAMA_CONTEXT_LENGTH": "4096",
            "OLLAMA_URL": "http://127.0.0.1:11436", "PYTHONUNBUFFERED": "1",
            "HF_HUB_DISABLE_TELEMETRY": "1", "DO_NOT_TRACK": "1",
            "VOICE_NOTEBOOK_RUN_ID": self.state["run_id"], "RUNTIME_PROFILE": self.profile,
        })
        subprocess.run(["git", "fetch", "--depth", "1", "origin", self.revision], cwd=self.root, check=True)
        target = subprocess.check_output(["git", "rev-parse", "FETCH_HEAD"], cwd=self.root, text=True).strip()
        current = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=self.root, text=True).strip()
        if current != target:
            dirty = subprocess.check_output(["git", "status", "--porcelain", "--untracked-files=no"], cwd=self.root, text=True).strip()
            if dirty or any(self.owns(role) for role in self.state["processes"]):
                raise RuntimeError("Repo có thay đổi hoặc demo đang chạy. Dừng bằng demo.stop() trước khi đổi revision; không tự reset source.")
            self.run(["git", "checkout", "--detach", target], label="checkout")
        self.manifest = json.loads((self.root / "config/model_manifest.json").read_text())
        profiles_file = self.root / "config/runtime_profiles.json"
        profiles = json.loads(profiles_file.read_text())
        profile = json.loads(json.dumps(profiles["profiles"]["colab-t4"]))
        if not self.gpu_for_asr_rag:
            for component in ("stt", "embedding", "reranker"):
                profile["placement"][component].update(device="cpu", dtype="float32")
        profiles["profiles"][self.profile] = profile
        self.effective_profile = profile
        signature = hashlib.sha256(json.dumps(dict(recipe=1, revision=target, cuda=self.cuda_index, profile=profile), sort_keys=True).encode()).hexdigest()
        if self.state.get("signature") != signature and any(self.owns(role) for role in self.state["processes"]):
            raise RuntimeError("Cấu hình đã đổi. Chạy demo.stop() rồi Run all để cài và khởi động lại đúng cấu hình.")
        if self.state.get("signature") != signature:
            self.state["stages"] = {}
        profiles_file.write_text(json.dumps(profiles, ensure_ascii=False, indent=2), encoding="utf-8")
        self.state.update(signature=signature, source_commit=target, platform=self.platform, gpu=gpu, profile=profile)
        self.save()
        print(f"Source: {target[:12]} | LLM/TTS: GPU | ASR/RAG: {'GPU' if self.gpu_for_asr_rag else 'CPU'}")

    def download(self, name):
        url, expected = ASSETS[name]
        path = self.storage / "downloads" / url.rsplit("/", 1)[-1]
        if path.exists() and file_sha(path) == expected:
            return path
        part = path.with_suffix(path.suffix + ".part")
        for attempt in range(3):
            offset = part.stat().st_size if part.exists() else 0
            request = urllib.request.Request(url, headers={"User-Agent": "Vietnamese-Voice-AI-Notebook", **({"Range": f"bytes={offset}-"} if offset else {})})
            try:
                with urllib.request.urlopen(request, timeout=60) as response:
                    resumed = response.status == 206 and response.headers.get("Content-Range", "").startswith(f"bytes {offset}-")
                    notified = time.monotonic()
                    with part.open("ab" if resumed else "wb") as output:
                        for block in iter(lambda: response.read(4 * 1024 * 1024), b""):
                            output.write(block)
                            if time.monotonic() - notified > 25:
                                print(f"  Tải {name}: {output.tell()/1024**2:.0f} MB", flush=True)
                                notified = time.monotonic()
                if file_sha(part) != expected:
                    part.unlink()
                    raise ValueError("Checksum không khớp")
                part.replace(path)
                return path
            except Exception:
                if attempt == 2:
                    raise
                print(f"Đang thử tải lại {name} ({attempt+2}/3)…", flush=True)
                time.sleep(2)

    def python(self, component):
        return self.storage / "envs" / component / "bin/python"

    def stage(self, name, action, probe):
        if self.state["stages"].get(name) == "DONE" and probe():
            print(f"✓ Dùng lại {name}", flush=True)
            return
        print(f"→ {name}", flush=True)
        self.state["stages"][name] = "RUNNING"
        self.save()
        try:
            action()
            if not probe():
                raise RuntimeError(f"{name}: kiểm tra chưa đạt. Xem orther/logs/probe-*.log.")
        except BaseException:
            self.state["stages"][name] = "FAILED"
            self.save()
            raise
        self.state["stages"][name] = "DONE"
        self.save()

    def import_probe(self, component, code):
        executable = self.python(component)
        if not executable.exists():
            return False
        with (self.storage / "logs" / f"probe-{component}.log").open("wb") as log:
            try:
                return subprocess.run([str(executable), "-c", code], cwd=self.root, env=self.env,
                                      stdout=log, stderr=subprocess.STDOUT, timeout=120).returncode == 0
            except subprocess.TimeoutExpired:
                return False

    def install(self):
        uv = self.storage / "tools/uv"
        if not uv.exists():
            archive = self.download("uv")
            with tarfile.open(archive, "r:gz") as tar:
                member = next(m for m in tar.getmembers() if m.isfile() and m.name.endswith("/uv"))
                with tar.extractfile(member) as source, uv.open("wb") as target:
                    shutil.copyfileobj(source, target)
            uv.chmod(0o755)
        self.uv = uv
        self.run([uv, "python", "install", "3.12"], label="python312")
        for component in ("tools", "stt", "rag", "llm", "tts", "app"):
            if not self.python(component).exists():
                self.run([uv, "venv", "--python", "3.12", self.python(component).parents[1]], label="venv-" + component)
        def pip(component, *specs, label=None):
            self.run([uv, "pip", "install", "--python", self.python(component), *specs], label=label or "install-" + component)
        self.stage("tools", lambda: pip("tools", "zstandard>=0.23,<1"), lambda: self.import_probe("tools", "import zstandard"))
        if not shutil.which("ffmpeg"):
            if os.geteuid() != 0:
                raise RuntimeError("Image thiếu ffmpeg và không có quyền cài system package; dùng image Colab/Kaggle tiêu chuẩn.")
            self.run(["apt-get", "update", "-qq"], label="apt-update")
            self.run(["apt-get", "install", "-y", "-qq", "ffmpeg", "libsndfile1"], label="system-audio")
        torch_index = self.cuda_index if self.gpu_for_asr_rag else "cpu"
        def install_stt():
            pip("stt", "--index-url", f"https://download.pytorch.org/whl/{torch_index}", "torch==2.11.0", "torchaudio==2.11.0")
            pip("stt", "-r", str(self.root / "services/stt/requirements.txt"))
        self.stage("STT", install_stt, lambda: self.import_probe("stt", "import torch, transformers, fastapi, silero_vad; assert torch.__version__.split('+')[0]=='2.11.0'"))
        def install_rag():
            pip("rag", "--index-url", f"https://download.pytorch.org/whl/{torch_index}", "torch==2.11.0")
            pip("rag", "-e", str(self.root / "services/rag") + "[api,ocr]")
        self.stage("RAG", install_rag, lambda: self.import_probe("rag", "import rag, torch, sentence_transformers, qdrant_client"))
        self.stage("LLM API", lambda: pip("llm", "-e", str(self.root / "services/llm") + "[api]"), lambda: self.import_probe("llm", "import fastapi, llm"))
        upstream = self.storage / "runtime/VieNeu-TTS"
        pinned = self.manifest["components"]["tts"]["upstream_commit"]
        if not (upstream / ".git").exists():
            self.run(["git", "clone", "--depth", "1", self.manifest["components"]["tts"]["upstream_repository"], upstream], label="clone-vieneu")
        self.run(["git", "fetch", "--depth", "1", "origin", pinned], cwd=upstream, label="fetch-vieneu")
        self.run(["git", "checkout", "--detach", pinned], cwd=upstream, label="checkout-vieneu")
        def install_tts():
            env_before = self.env.get("UV_PROJECT_ENVIRONMENT")
            self.env["UV_PROJECT_ENVIRONMENT"] = str(self.python("tts").parents[1])
            try:
                self.run([uv, "sync", "--project", upstream, "--frozen", "--python", "3.12"], label="vieneu-core")
            finally:
                if env_before is None:
                    self.env.pop("UV_PROJECT_ENVIRONMENT", None)
                else:
                    self.env["UV_PROJECT_ENVIRONMENT"] = env_before
            pip("tts", "--index-url", f"https://download.pytorch.org/whl/{self.cuda_index}", "torch==2.8.0", "torchaudio==2.8.0")
            pip("tts", "transformers==4.57.6", "accelerate>=1,<2", "safetensors>=0.4,<1", "fastapi>=0.115,<1", "uvicorn[standard]>=0.30,<1", "pydantic>=2.8,<3")
        expected_tts = self.manifest["components"]["tts"].get("runtime_version", "3.8.3")
        self.stage("TTS CUDA", install_tts, lambda: self.import_probe("tts", f"import vieneu,torch,transformers,importlib.metadata; assert importlib.metadata.version('vieneu')=={expected_tts!r}; assert torch.__version__.split('+')[0]=='2.8.0'; assert torch.cuda.is_available(); x=torch.ones(8,device='cuda'); assert (x+x).sum().item()==16"))
        self.stage("web", lambda: pip("app", "-e", str(self.root / "app") + "[demo]"), lambda: self.import_probe("app", "import voice_app.web, fastapi, numpy"))
        self.run([self.python("tts"), "scripts/prefetch_tts.py", "--profile", self.profile], label="prefetch-tts")
        ollama = self.storage / "tools/ollama/bin/ollama"
        if not ollama.exists():
            archive = self.download("ollama")
            code = "import sys,tarfile,zstandard; from pathlib import Path; p=Path(sys.argv[2]); p.mkdir(parents=True,exist_ok=True); r=zstandard.ZstdDecompressor().stream_reader(open(sys.argv[1],'rb')); t=tarfile.open(fileobj=r,mode='r|'); t.extractall(p,filter='data')"
            self.run([self.python("tools"), "-c", code, archive, ollama.parents[1]], label="extract-ollama")
            if not ollama.exists():
                raise RuntimeError("Không tìm thấy bin/ollama sau khi giải nén.")
            archive.unlink()  # Installer only; keep models, datasets and caches.
        self.ollama = ollama
        self.env["PATH"] = str(ollama.parent) + os.pathsep + self.env.get("PATH", "")
        for component in ("stt", "rag", "llm", "tts", "app"):
            self.run([uv, "pip", "freeze", "--python", self.python(component)], label="packages-" + component, quiet=True)
        print("✓ Cài đặt và kiểm tra CUDA xong. Không nạp tài liệu smoke.")

    def owns(self, role):
        pid = self.state.get("processes", {}).get(role, {}).get("pid")
        if not isinstance(pid, int) or pid <= 1:
            return False
        try:
            marker = f"VOICE_NOTEBOOK_RUN_ID={self.state['run_id']}".encode()
            return marker in Path(f"/proc/{pid}/environ").read_bytes().split(b"\0")
        except OSError:
            return False

    def launch(self, role, argv, port=None, extra_env=None):
        if self.owns(role):
            return
        if port:
            with socket.socket() as probe:
                if probe.connect_ex(("127.0.0.1", port)) == 0:
                    raise RuntimeError(f"Cổng {port} đang do tiến trình khác dùng; không tự tắt tiến trình đó.")
        path = self.storage / "logs" / (role + ".log")
        with path.open("ab") as log:
            process = subprocess.Popen(list(map(str, argv)), cwd=self.root, env=extra_env or self.env,
                                       stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, start_new_session=True)
        self.processes[role] = process
        self.state["processes"][role] = {"pid": process.pid, "argv": list(map(str, argv))}
        self.save()

    @staticmethod
    def http_json(url, payload=None, timeout=10):
        request = urllib.request.Request(url, data=json.dumps(payload).encode() if payload is not None else None,
                                         headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.load(response)

    def wait(self, url, role, timeout=1800):
        started = time.monotonic()
        notified = started
        while time.monotonic() - started < timeout:
            if not self.owns(role):
                raise RuntimeError(f"{role} đã dừng.\n{self.tail(role+'.log', 28)}")
            try:
                return self.http_json(url)
            except Exception:
                if time.monotonic() - notified > 25:
                    print(f"  Đang chờ {role} sẵn sàng ({int(time.monotonic()-started)} giây)…", flush=True)
                    notified = time.monotonic()
                time.sleep(2)
        raise TimeoutError(f"{role} chưa sẵn sàng.\n{self.tail(role+'.log', 28)}")

    def ensure_llm(self):
        model = self.manifest["components"]["llm"]
        expected = normalized_digest(model["manifest_digest"])
        tags = self.http_json("http://127.0.0.1:11436/api/tags").get("models", [])
        installed = listed_model(tags, model["model_id"])
        report = {"model": model["model_id"], "expected_digest": expected,
                  "installed_before": installed, "checked_at": datetime.now(timezone.utc).isoformat()}
        report_path = self.storage / "runtime/ollama-model-check.json"

        def record():
            report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

        record()
        if not model_matches(installed, expected):
            if model["model_id"] != OLLAMA_PIN["model_id"]:
                raise RuntimeError("Model chưa đúng pin và không thuộc cấu hình notebook hỗ trợ; xem " + str(report_path))
            # Check the immutable expected hash against the tag BEFORE downloading
            # gigabytes. Check again through Ollama after pull to catch tag races.
            request = urllib.request.Request(OLLAMA_PIN["registry_url"], headers={"Accept": "application/vnd.docker.distribution.manifest.v2+json"})
            with urllib.request.urlopen(request, timeout=30) as response:
                raw = response.read(1024 * 1024 + 1)
            actual = hashlib.sha256(raw).hexdigest()
            report.update(registry_url=OLLAMA_PIN["registry_url"], registry_digest=actual)
            record()
            if actual != expected:
                raise RuntimeError(f"Nhãn {model['model_id']} trên registry không khớp pin.\nMong đợi: {expected}\nRegistry: {actual}\nKhông tải lại model. Chi tiết: {report_path}")
            self.run([self.ollama, "pull", model["model_id"]], label="pull-llm")
        tags = self.http_json("http://127.0.0.1:11436/api/tags").get("models", [])
        installed = listed_model(tags, model["model_id"])
        report["installed_after"] = installed
        report["passed"] = model_matches(installed, expected)
        record()
        if not report["passed"]:
            actual = installed.get("digest") if installed else "không tìm thấy model"
            raise RuntimeError(f"Ollama model chưa đúng pin.\nMong đợi: {expected}\nThực nhận: {actual}\nChi tiết: {report_path}")
        print(f"✓ LLM {model['model_id']}: digest {expected[:12]} đã khớp; không tải lại khi đã có.")

    def start(self):
        self.launch("ollama", [self.ollama, "serve"], 11436)
        self.wait("http://127.0.0.1:11436/api/tags", "ollama", 120)
        self.ensure_llm()
        model = self.manifest["components"]["llm"]
        self.launch("stack", [self.python("app"), "scripts/start_services.py", "--profile", self.profile, "--with-web"], 7860)
        self.wait("http://127.0.0.1:7860/health/live", "stack")
        tts = self.http_json("http://127.0.0.1:8003/health/ready")
        if tts.get("backend") != "pytorch" or "cuda" not in str(tts.get("device")):
            raise RuntimeError("TTS chưa thực sự chạy PyTorch/CUDA; xem tts.log.")
        print("→ Nạp LLM lên GPU (một lượt khởi động ngắn, không phải benchmark)…")
        self.http_json("http://127.0.0.1:11436/api/generate", {"model": model["model_id"], "prompt": "Xin chào.", "think": False, "stream": False, "keep_alive": "30m", "options": {"num_predict": 8, "num_ctx": 4096, "num_gpu": -1}}, timeout=300)
        running = self.http_json("http://127.0.0.1:11436/api/ps").get("models", [])
        active = listed_model(running, model["model_id"])
        if not active or active.get("size_vram", 0) <= 0:
            raise RuntimeError("LLM chưa có bộ nhớ GPU. Kiểm tra driver/VRAM và ollama.log.")
        readiness = self.http_json("http://127.0.0.1:7860/health/ready", timeout=30)
        (self.storage / "runtime/readiness.json").write_text(json.dumps(readiness, ensure_ascii=False, indent=2), encoding="utf-8")
        require_ready(readiness)
        print("✓ Web sẵn sàng. TTS CUDA và LLM GPU đã kiểm tra; kho tri thức mới có thể đang trống.")

    def tunnel(self):
        require_ready(self.http_json("http://127.0.0.1:7860/health/ready", timeout=30))
        binary = self.storage / "tools/cloudflared"
        if not binary.exists():
            shutil.copyfile(self.download("cloudflared"), binary)
            binary.chmod(0o755)
        if not self.owns("cloudflared"):
            (self.storage / "logs/cloudflared.log").write_text("", encoding="utf-8")
            config = self.storage / "runtime/cloudflared.yml"
            config.write_text("# Isolated Quick Tunnel config\n", encoding="utf-8")
            env = dict(self.env)
            for key in ("TUNNEL_TOKEN", "TUNNEL_TOKEN_FILE", "TUNNEL_ORIGIN_CERT"):
                env.pop(key, None)
            self.launch("cloudflared", [binary, "tunnel", "--config", config, "--no-autoupdate", "--protocol", "http2", "--url", "http://127.0.0.1:7860"], extra_env=env)
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            url = find_tunnel_url(self.tail("cloudflared.log", 100))
            if url:
                self.state["public_url"] = url
                self.save()
                try:
                    self.http_json(url + "/health/live", timeout=12)
                    print(f"\nLINK DEMO: {url}\n")
                    return url
                except Exception:
                    pass
            if not self.owns("cloudflared"):
                break
            time.sleep(2)
        raise RuntimeError("Chưa kiểm chứng được link Cloudflare. Kiểm tra Internet/tunnel egress của nền tảng.\n" + self.tail("cloudflared.log", 30))

    def keep_alive(self, minutes):
        print("Giữ phiên notebook mở để dùng demo. Dừng bằng demo.stop() trong ô mới.")
        deadline = time.monotonic() + max(0, minutes) * 60
        while time.monotonic() < deadline:
            for role in ("ollama", "stack", "cloudflared"):
                if not self.owns(role):
                    raise RuntimeError(f"{role} đã dừng.\n{self.tail(role+'.log')}")
            time.sleep(min(30, max(0, deadline-time.monotonic())))

    def stop(self):
        for role in ("cloudflared", "stack", "ollama"):
            if not self.owns(role):
                continue
            pid = self.state["processes"][role]["pid"]
            try:
                if os.getpgid(pid) == pid:
                    os.killpg(pid, signal.SIGTERM)
                    deadline = time.monotonic() + 12
                    while self.owns(role) and time.monotonic() < deadline:
                        if role in self.processes:
                            self.processes[role].poll()
                        time.sleep(.2)
                    if self.owns(role):
                        os.killpg(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            self.state["processes"].pop(role, None)
        self.save()
        print("Đã gửi lệnh dừng các tiến trình demo thuộc notebook này; giữ nguyên dữ liệu/model.")
