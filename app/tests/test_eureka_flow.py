import shutil
import subprocess
from pathlib import Path

import pytest

from test_media_v10 import SlowTTS, build
from voice_app.media_v10 import V10MediaPipeline
from voice_app.realtime.speech_units import SpeechUnitChunker, SentenceSpeechChunker


def test_streamed_decimal_and_abbreviation_do_not_split_at_network_edge():
    chunker = SpeechUnitChunker(min_chars=10, target_chars=90, max_chars=160)
    out = []
    for delta in ["Tỷ lệ là 1.", "5 phần trăm tại TP.", " Hồ Chí Minh. "]:
        out.extend(chunker.push(delta))
    out.extend(chunker.flush())
    assert out == ["Tỷ lệ là 1.5 phần trăm tại TP. Hồ Chí Minh."]


def test_final_sentence_without_lookahead_flushes_once():
    c = SpeechUnitChunker()
    assert c.push("Xin chào.") == []
    assert c.flush() == ["Xin chào."]
    assert c.flush() == []


def test_sentence_path_does_not_cut_at_smart_chunk_target_or_comma():
    text = "Trường hỗ trợ người học, giảng viên và nghiên cứu viên, với các thông tin được lưu trong kho tri thức."
    c = SentenceSpeechChunker()
    out = []
    for word in text.split():
        out.extend(c.push(word + " "))
    out.extend(c.flush())
    assert out == [text]


def test_active_pipeline_uses_complete_sentences_by_default(tmp_path):
    core = build(tmp_path)
    events = list(V10MediaPipeline(core).stream_turn(query_text="V10?", rag_mode="dense", rerank=False, top_k=1))
    assert len(core.tts.calls) == 3
    assert all(text.endswith(".") for text in core.tts.calls)
    meta = next(e["meta"] for e in events if e["type"] == "tts_done")
    assert meta["speech_segmentation_mode"] == "sentence"
    assert meta["complete_unit_buffering"] is True


def test_sentence_path_preserves_decimal_and_final_tail():
    c = SentenceSpeechChunker()
    out = []
    for delta in ["Tỷ lệ là 1.", "5 phần trăm tại TP.", " Hồ Chí Minh. ", "Cảm ơn bạn"]:
        out.extend(c.push(delta))
    out.extend(c.flush())
    assert out == ["Tỷ lệ là 1.5 phần trăm tại TP. Hồ Chí Minh.", "Cảm ơn bạn"]


def test_pcm_is_published_only_when_its_complete_unit_is_available(tmp_path):
    core = build(tmp_path)
    finished = set()

    class ObservedTTS(SlowTTS):
        def stream_native_pcm(self, text, **kwargs):
            for event in super().stream_native_pcm(text, **kwargs):
                if event["type"] == "done":
                    finished.add(kwargs["unit_index"])
                yield event

    core.tts = ObservedTTS(tmp_path)
    pcm = []
    for event in V10MediaPipeline(core).stream_turn(query_text="V10?", rag_mode="dense", rerank=False, top_k=1):
        if event["type"] == "pcm":
            assert event["unit_index"] in finished
            pcm.append(event)
    assert pcm
    assert [p["chunk_index"] for p in pcm] == list(range(1, len(pcm)+1))
    assert all(len(p["raw"]) == 400 for p in pcm)


def test_failed_partial_unit_does_not_leak_a_broken_fragment(tmp_path, monkeypatch):
    import threading
    import time
    from voice_app.realtime.speech_units import SpeechUnitScheduler

    core = build(tmp_path)
    original_close = SpeechUnitScheduler.close

    def close_after_terminal_is_queued(scheduler):
        if scheduler.cancel_event.is_set():
            time.sleep(0.03)
        return original_close(scheduler)

    monkeypatch.setattr(SpeechUnitScheduler, "close", close_after_terminal_is_queued)

    class FailingTTS(SlowTTS):
        def stream_native_pcm(self, text, **kwargs):
            for event in super().stream_native_pcm(text, **kwargs):
                yield event
                raise RuntimeError("lost upstream after partial PCM")

    core.tts = FailingTTS(tmp_path)
    events = []
    worker = threading.Thread(target=lambda: events.extend(V10MediaPipeline(core).stream_turn(query_text="V10?", rag_mode="dense", rerank=False, top_k=1)), daemon=True)
    worker.start()
    worker.join(timeout=3)
    assert not worker.is_alive(), "cancellation discarded the media sentinel and hung the turn"
    assert any(e["type"] == "error" for e in events)
    assert not any(e["type"] == "pcm" for e in events)


def test_actual_browser_scripts_endpoint_and_fifo_behaviour():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node required to execute real shipped frontend scripts")
    result = subprocess.run([node, str(Path(__file__).with_name("browser_audio_regression.cjs"))], capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr
    assert '"passed": 6' in result.stdout
