"""Small actual-model probe. Writes new evidence; never overwrites benchmarks."""
import argparse
import json
import statistics
import time
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
from voice_app.clients.tts import TTSClient


def measure(url, runs=3, voice_name="Hải Đăng"):
    root = Path(__file__).resolve().parents[1]
    out = root / "orther/artifacts/tts-runtime" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    out.mkdir(parents=True, exist_ok=False)
    with httpx.Client(timeout=180) as client:
        health = client.get(url.rstrip("/") + "/health/ready")
        health.raise_for_status()
        health = health.json()
        catalog = client.get(url.rstrip("/") + "/api/voices")
        catalog.raise_for_status()
        options = catalog.json()["voices"]
        voice = next((v for v in options if v["id"] == voice_name), None)
        if voice is None:
            raise RuntimeError(f"Không có giọng {voice_name}; kiểm tra phiên bản VieNeu.")
        report = {"health": health, "voice": voice, "rows": [],
                  "measurement": {"http_ttfb_ms": "client perf_counter: POST submission to first nonempty HTTP body bytes",
                                  "first_complete_pcm_ms": "client perf_counter: stream call to first complete decoded TTS1 PCM frame",
                                  "http_rtf": "HTTP request to stream EOF divided by decoded PCM frames/48000; includes local transport",
                                  "native_warmup": "service perf_counter: infer_stream entry to generator yields/EOF; see health.warmup",
                                  "physical_speaker": "not measured", "llm_ttft": "not part of this TTS probe"}}
        path = out / "results.json"
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        texts = ["Xin chào, mình là trợ lý giọng nói tiếng Việt.",
                 "Bạn có thể nhập câu hỏi hoặc dùng micro để nói. Mình sẽ tìm thông tin trong tài liệu và đọc câu trả lời cho bạn."]
        tts = TTSClient(url, output_dir=out, sample_rate=48000)
        try:
            for run in range(1, runs + 1):
                for index, text in enumerate(texts, 1):
                    parts = []
                    frames = 0
                    first_pcm_ms = None
                    started = time.perf_counter()
                    terminal = None
                    for event in tts.stream_native_pcm(text, voice_index=voice["index"], unit_index=index):
                        if event["type"] == "audio":
                            if first_pcm_ms is None:
                                first_pcm_ms = (time.perf_counter() - started) * 1000
                            parts.append(event["raw"])
                            frames += event["frame_count"]
                        elif event["type"] == "done":
                            terminal = event
                    if terminal is None:
                        raise RuntimeError("TTS không trả trạng thái hoàn tất")
                    wav = tts.save_pcm_wav(b"".join(parts), prefix=f"run-{run}-text-{index}")
                    report["rows"].append({"run": run, "text": text, "http_ttfb_ms": terminal["ttfb_ms"],
                                           "first_complete_pcm_ms": first_pcm_ms,
                                           "http_rtf": terminal["rtf"], "audio_ms": terminal["audio_duration_ms"],
                                           "pcm_frames": frames, "peak": terminal["peak"], "wav": wav,
                                           "chunks": terminal["emitted_chunk_count"], "total_ms": terminal["total_ms"]})
                    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
                    print(json.dumps(report["rows"][-1], ensure_ascii=False), flush=True)
        finally:
            tts.close()
        report["summary"] = {"median_http_ttfb_ms": statistics.median(r["http_ttfb_ms"] for r in report["rows"]),
                              "median_http_rtf": statistics.median(r["http_rtf"] for r in report["rows"]),
                              "requests": len(report["rows"])}
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print("TTS measurements:", path, flush=True)
        return path


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8003")
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--voice", default="Hải Đăng")
    args = parser.parse_args()
    measure(args.url, max(1, min(5, args.runs)), args.voice)
