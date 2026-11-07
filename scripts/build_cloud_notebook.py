"""Build a notebook which clones released source; no runtime code patches."""
from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "notebooks/CHAY_VIETNAMESE_VOICE_AI_COLAB_KAGGLE.ipynb"


def cell(kind, source, name, **metadata):
    result = {"cell_type": kind, "id": name, "metadata": metadata,
              "source": source.splitlines(keepends=True)}
    if kind == "code":
        result.update(execution_count=None, outputs=[])
    return result


def build(revision=None):
    revision = revision or subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    if not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ValueError("Notebook phát hành phải khóa một Git commit đầy đủ.")
    helper = (ROOT / "scripts/cloud_notebook_runtime.py").read_text(encoding="utf-8")
    cells = [
        cell("markdown", """# Vietnamese Voice AI — Colab / Kaggle

**Bật GPU + Internet → Run all / Chạy tất cả → mở LINK DEMO ở bước 5.**

- **Colab:** Runtime → Change runtime type → GPU. Không cần gắn Google Drive.
- **Kaggle:** Settings → Accelerator → GPU; bật Internet. Tài khoản chưa xác minh có thể chưa bật được Internet.
- Không cần API key hay tài khoản Cloudflare. Lần đầu tải thư viện/model có thể mất nhiều phút tùy mạng và dung lượng.
- VieNeu SDK **3.8.3**, upstream commit **6cdb62e03e6a9fd6ebff70e77aff8570c50949c3**, v3 Turbo 48 kHz, **25 giọng**, mặc định **Hải Đăng**. Giữ STT/RAG/LLM như manifest.
- LLM và TTS chạy GPU. ASR/RAG mặc định CPU để giảm VRAM/dung lượng; có thể bật GPU cho hai phần này ở ô cấu hình.
- Notebook lấy mã nguồn đã sửa từ GitHub, **không ghi đè source bằng bản vá và không cần chèn thêm ô trước bước 4**. Digest LLM khóa trong manifest, kiểm tra trước/sau pull; không tự chấp nhận bất kỳ digest đang cài.
- Kho tri thức mới có thể trống. Tải tài liệu thật qua giao diện; không tự tạo tài liệu thử.
- Công cụ, môi trường, model, cache và log nằm trong **`orther/` của repo vừa clone**.

Link Cloudflare công khai tạm thời, hết hiệu lực khi tunnel/runtime dừng. Chỉ chia sẻ cho người demo; không đưa dữ liệu bí mật lên phiên công khai. Đây không phải dịch vụ chạy thường trực.
""", "intro"),
        cell("code", f"""# 1. Cấu hình — thường giữ nguyên rồi Run all.
REPO_REVISION = {revision!r}
GPU_FOR_ASR_RAG = False
MEASURE_TTS = True  # Đo 6 câu ngắn/vừa; có thể tắt để mở link sớm hơn.
CUDA_INDEX = "auto"  # P100/T4/A100: cu126; Blackwell: cu128.
KEEP_ALIVE_MINUTES = 60
""", "settings"),
        cell("markdown", """## Bộ khởi chạy

Ô dưới định nghĩa công cụ khởi chạy, checkpoint, kiểm tra checksum và quản lý tiến trình của riêng notebook. Các dịch vụ dùng nguyên mã nguồn trong commit đã khóa. Không tự tắt tiến trình lạ hoặc ghi đè source đã được bạn chỉnh sửa.
""", "helper-info"),
        cell("code", helper, "runtime-helper", collapsed=True, jupyter={"source_hidden": True}),
        cell("code", """# 2. Kiểm tra GPU, Internet, dung lượng và clone đúng commit.
demo = CloudDemo(revision=REPO_REVISION, gpu_for_asr_rag=GPU_FOR_ASR_RAG,
                 cuda_index=CUDA_INDEX)
demo.prepare()
""", "prepare"),
        cell("code", """# 3. Cài môi trường riêng và tải model đã khóa.
# Python 3.12 riêng giúp tránh lỗi venv/ensurepip của kernel Colab.
demo.install()
""", "install"),
        cell("code", """# 4. Khởi động dịch vụ, xác minh model/GPU/readiness.
demo.start()
if MEASURE_TTS:
    demo.run([demo.python("app"), "scripts/measure_tts_runtime.py", "--runs", "3"],
             label="measure-tts", timeout=600)
    print(demo.tail("measure-tts.log", 8))
""", "services"),
        cell("code", """# 5. Tạo link HTTPS và kiểm tra truy cập công khai.
from IPython.display import Markdown, display
public_url = demo.tunnel()
display(Markdown(f"## [Mở Vietnamese Voice AI]({public_url})\\n\\n{public_url}"))
print("Cho phép dùng micro. Bấm gửi một câu để trình duyệt cho phép phát âm thanh.")
print("Log, checkpoint, số đo và WAV:", demo.storage)
""", "public-link"),
        cell("markdown", """## Giữ phiên và xử lý lỗi

**Link dùng được ngay khi ô cuối còn chạy.** Ô cuối giữ notebook hoạt động trong thời gian cấu hình, không vượt giới hạn nền tảng.

- Dừng: ngắt ô cuối, mở ô mới và chạy `demo.stop()`. Chỉ dừng tiến trình do notebook quản lý; giữ model và tài liệu trong phiên.
- Cùng phiên, cùng cấu hình: chạy lại từ bước lỗi hoặc Run all. Các phần đã cài được kiểm tra và dùng lại.
- Đổi từ notebook cũ có ô vá: nên dùng runtime mới cho bản phát hành này. Nếu thư mục cũ có chỉnh sửa, notebook từ chối checkout thay vì xóa thay đổi. Xuất tài liệu cần giữ trước khi đổi runtime.
- Runtime bị xóa/cấp máy mới: cần tải và cài lại; URL sẽ đổi. Tài liệu ở `orther/data/notebook-demo/rag`, cần sao lưu trước khi đóng phiên. Lịch sử hội thoại hiện lưu trong RAM.
- Lỗi cài: `print(demo.tail("install-stt.log", 40))`, `print(demo.tail("install-rag.log", 40))`, `print(demo.tail("install-tts.log", 40))`.
- Lỗi dịch vụ: `print(demo.tail("stack.log", 40))`, `print(demo.tail("tts.log", 40))`, `print(demo.tail("ollama.log", 40))`.
- CUDA: `print(demo.tail("probe-tts.log", 40))`; kiểm GPU/driver/CUDA_INDEX. Không ghi nhận CPU fallback thành GPU.
- Digest LLM: đọc `orther/runtime/ollama-model-check.json`, có pin mong đợi và digest thực nhận. Không sửa pin theo bất kỳ model đang cài để bỏ qua kiểm tra.
- Số đo TTS: `print(demo.tail("measure-tts.log", 20))`; JSON/WAV trong `orther/artifacts/tts-runtime/`. TTFB là thời gian HTTP nhận byte đầu; khung PCM hoàn chỉnh và RTF lưu riêng. Đây không phải TTFT của LLM.
- Tunnel: `print(demo.tail("cloudflared.log", 40))`; kiểm Internet và hạn chế kết nối của nền tảng.

**Đã kiểm thử:** VieNeu 3.8.3 CUDA/Colab qua trình duyệt thật, CPU/ONNX độc lập, PCM 48 kHz và hủy/phát/chạy chữ. Chưa khẳng định mọi GPU/Kaggle đều cho cùng tốc độ; chưa chấm MOS hoặc đo loa vật lý. Xem `docs/VIENEU_383_UPGRADE.md` trong repo.

[Mã nguồn](https://github.com/ntd2k5-2005/Vietnamese-AI-Voice-Assistance) · [Cloudflare Quick Tunnels](https://developers.cloudflare.com/tunnel/get-started/quick-tunnels/)
""", "operations"),
        cell("code", "demo.keep_alive(KEEP_ALIVE_MINUTES)\n", "keep-alive"),
    ]
    notebook = {"nbformat": 4, "nbformat_minor": 5, "cells": cells,
                "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
                             "language_info": {"name": "python", "version": "3.12"},
                             "colab": {"name": OUTPUT.name, "provenance": []}, "accelerator": "GPU"}}
    data = json.dumps(notebook, ensure_ascii=False, indent=1) + "\n"
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(data, encoding="utf-8")
    (ROOT.parent / OUTPUT.name).write_text(data, encoding="utf-8")
    return OUTPUT


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--revision")
    print(build(parser.parse_args().revision))
