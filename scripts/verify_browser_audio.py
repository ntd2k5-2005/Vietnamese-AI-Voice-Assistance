"""Local production gateway/browser regression with explicitly synthetic services.

No models, downloads, paid APIs or KLTN services. Evidence is not a model benchmark.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
OUT = Path(os.environ.get("VOICE_BROWSER_EVIDENCE_DIR", ROOT / "orther/artifacts/browser-flow"))
sys.path[:0] = [str(ROOT / "app"), str(ROOT / "app/tests")]


def serve(buffered):
    import numpy as np
    import uvicorn
    from scipy.io import wavfile
    from test_media_v10 import FakeSTT, FakeRAG, FastLLM, SlowTTS
    from voice_app.config import AppSettings
    from voice_app.orchestrator import VoiceOrchestrator
    import voice_app.web as web

    class LLM(FastLLM):
        def chat_stream(self, *args, **kwargs):
            for part in ("Xin chào bạn. ", "Mình sẵn sàng lắng nghe câu hỏi của bạn."):
                yield {"type": "delta", "content": part}
            yield {"type": "done", "metrics": {}}

    class TTS(SlowTTS):
        def list_voices(self):
            return {"voices": [{"id": "fixture", "name": "Giọng kiểm thử", "label": "Giọng kiểm thử", "index": 0, "default": True}]}

        def stream_native_pcm(self, text, **kwargs):
            # Deliberately slower than realtime, same samples and schedule
            # across both runs: demonstrate starvation, not model performance.
            for _ in range(10):
                time.sleep(0.35)
                audio = (0.1*np.sin(2*np.pi*220*np.arange(9600)/48000)).astype("<f4")
                yield {"type": "audio", "raw": audio.tobytes(), "duration_ms": 200, "frame_count": len(audio)}
            yield {"type": "done", "rtf": None}

        def save_pcm_wav(self, raw, *, prefix):
            name = OUT / (prefix + ".wav")
            wavfile.write(name, 48000, np.frombuffer(raw, dtype="<f4"))
            return str(name)

    settings = AppSettings(_env_file=None, tts_buffer_complete_units=buffered, tts_output_dir=OUT)
    core = VoiceOrchestrator(settings, stt_client=FakeSTT(), rag_client=FakeRAG(), llm_client=LLM(), tts_client=TTS(OUT))
    with patch.object(web, "AppSettings", return_value=settings), patch.object(web, "VoiceOrchestrator", return_value=core):
        app = web.create_app()
    uvicorn.run(app, host="127.0.0.1", port=18760)


def main(microphone=False):
    import httpx
    import socket
    from playwright.sync_api import sync_playwright

    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 18760))  # Refuse to use an existing service.
    results = []
    if microphone:
        import numpy as np
        from scipy.io import wavfile
        samples = np.zeros(48000*8, dtype=np.float32)
        samples[24000:72000] = 0.1*np.sin(2*np.pi*220*np.arange(48000)/48000)
        wavfile.write(OUT / "synthetic-mic.wav", 48000, (samples*32767).astype(np.int16))
    for buffered in ((True,) if microphone else (False, True)):
        label = "microphone-endpoint" if microphone else "buffered-units" if buffered else "direct-frames"
        with (OUT / (label + ".log")).open("w", encoding="utf-8") as log:
            process = subprocess.Popen([sys.executable, __file__, "--serve", "--buffered", str(int(buffered))], cwd=ROOT, stdout=log, stderr=log, env=os.environ.copy())
            try:
                for _ in range(100):
                    if process.poll() is not None:
                        raise RuntimeError("Fixture gateway exited; inspect " + str(log.name))
                    try:
                        if httpx.get("http://127.0.0.1:18760/health/live", timeout=1).status_code == 200:
                            break
                    except httpx.HTTPError:
                        pass
                    time.sleep(0.2)
                else:
                    raise TimeoutError("Fixture gateway startup")
                with sync_playwright() as pw:
                    flags = []  # Exercise normal user-gesture autoplay policy.
                    if microphone:
                        flags.extend(["--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream", "--use-file-for-fake-audio-capture=" + str(OUT / "synthetic-mic.wav")])
                    browser = pw.chromium.launch(channel="chrome", headless=True, args=flags)
                    page = browser.new_page(viewport={"width": 1100, "height": 800})
                    page.goto("http://127.0.0.1:18760")
                    page.wait_for_function("typeof handleWorkletMessage === 'function'")
                    page.evaluate("""() => {
                      window.__audioEvents=[];
                      window.__textEvents=[];
                      const render=updateAssistant;
                      updateAssistant=(id,text)=>{
                        window.__textEvents.push({text,time:performance.now(),consumed:spokenFrames});
                        render(id,text);
                      };
                      const original=handleWorkletMessage;
                      handleWorkletMessage=msg=>{
                        if(['started','resumed','rebuffering','drained','consuming'].includes(msg.type))
                          window.__audioEvents.push({...msg,time:performance.now()});
                        original(msg);
                      };
                    }""")
                    if microphone:
                        page.locator("#micBtn").click()
                        page.wait_for_function("pttRecording", timeout=10000)
                        page.wait_for_function("turnBusy && !pttRecording", timeout=15000)
                    else:
                        page.locator("#question").fill("Xin chào")
                        page.locator("#sendBtn").click()
                    page.wait_for_function("serverTurnDone && playbackDrained && !turnBusy", timeout=40000)
                    row = page.evaluate("""() => ({events:window.__audioEvents,text_events:window.__textEvents,accepted:bm.pcm_trace.length,
                      underruns:bm.underrun_count,rebuffer:bm.rebuffer_count,turnBusy,
                      text:document.querySelector('.message.assistant')?.innerText})""")
                    row.update(mode=label, fixture="synthetic_sine_PCM_and_stub_LLM_not_model_inference")
                    page.screenshot(path=str(OUT / (label + ".png")), full_page=True)
                    page.set_viewport_size({"width": 390, "height": 844})
                    page.screenshot(path=str(OUT / (label + "-narrow.png")), full_page=True)
                    browser.close()
                    results.append(row)
            finally:
                process.terminate()
                process.wait(timeout=15)
    (OUT / ("mic-result.json" if microphone else "result.json")).write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    assert all(any(e["type"] == "drained" for e in r["events"]) for r in results)
    for row in results:
        first_spoken_text = next(e for e in row["text_events"] if e["text"] and e["text"] != "…")
        first_played = next(e for e in row["events"] if e["type"] == "started")
        assert first_spoken_text["time"] >= first_played["time"]
        assert first_spoken_text["consumed"] > 0
    if not microphone:
        assert results[1]["underruns"] < results[0]["underruns"], results
    print(json.dumps([{k: v for k, v in r.items() if k not in {"events", "text_events"}} for r in results], ensure_ascii=False))


if __name__ == "__main__":
    args = argparse.ArgumentParser()
    args.add_argument("--serve", action="store_true")
    args.add_argument("--buffered", type=int, default=1)
    args.add_argument("--mic", action="store_true")
    values = args.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    if values.serve:
        serve(bool(values.buffered))
    else:
        main(values.mic)
