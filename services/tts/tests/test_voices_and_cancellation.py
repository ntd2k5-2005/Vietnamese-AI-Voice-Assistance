import asyncio
import threading
from types import SimpleNamespace

import numpy as np
import pytest
from fastapi.testclient import TestClient

import api


def setup_model(monkeypatch):
    class Presets:
        _default_voice = "Hải Đăng"
        def resolve_voice_name(self, name):
            return {"Minh Quân": "Hải Đăng"}.get(name, name)
        def get_preset_voice(self, name):
            return {"name": name, "speaker_emb": [1, 2], "codes": [3]}
        def infer_stream(self, **kwargs):
            yield np.ones(3840, dtype=np.float32) * 0.1
    model = Presets()
    monkeypatch.setattr(api, "model", model)
    monkeypatch.setattr(api, "voices", [("⭐ Hải Đăng", "Hải Đăng"), ("Trúc Ly", "Trúc Ly")])
    monkeypatch.setattr(api, "_stream_slots", threading.BoundedSemaphore(1))
    return model


def test_voice_catalog_is_named_without_speaker_embeddings(monkeypatch):
    setup_model(monkeypatch)
    response = TestClient(api.app).get("/api/voices")
    assert response.status_code == 200
    rows = response.json()["voices"]
    assert rows[0]["id"] == "Hải Đăng" and rows[0]["default"] is True
    assert rows[1]["label"] == "Trúc Ly"
    assert all("speaker_emb" not in row and "codes" not in row for row in rows)


def test_named_and_legacy_voice_requests_produce_pcm48k(monkeypatch):
    setup_model(monkeypatch)
    client = TestClient(api.app)
    for selection in ({"voice_id": "Hải Đăng"}, {"voice_id": "Minh Quân"}, {"voice_index": 1}, {}):
        response = client.post("/api/tts", json={"text": "Xin chào", **selection})
        assert response.status_code == 200
        assert response.headers["x-audio-sample-rate"] == "48000"
        assert response.headers["x-audio-dtype"] == "float32"
        assert len(response.content) == 3840 * 4
    assert client.post("/api/tts", json={"text": "Xin chào", "voice_id": "Giọng không tồn tại"}).status_code == 422


def test_native_iterator_is_closed_on_cancellation(monkeypatch):
    model = setup_model(monkeypatch)
    closed = []
    def stream(**kwargs):
        try:
            yield np.ones(48, dtype=np.float32)
            yield np.ones(48, dtype=np.float32)
        finally:
            closed.append(True)
    model.infer_stream = stream
    generator = api.iter_model_audio_traced("Xin chào", selected_voice=None, pre_chunked=True)
    next(generator)
    generator.close()
    assert closed == [True]


def test_disconnect_before_response_body_releases_stream_slot(monkeypatch):
    setup_model(monkeypatch)
    response = api.generate_tts(api.TTSRequest(text="Xin chào"))
    async def receive():
        return {"type": "http.disconnect"}
    async def send(message):
        raise OSError("client disconnected")
    async def run():
        try:
            await response({"type": "http", "asgi": {"spec_version": "2.4"}}, receive, send)
        except Exception:
            pass
    asyncio.run(run())
    assert api._stream_slots.acquire(blocking=False)


def test_live_stream_does_not_buffer_a_complete_sentence(tmp_path):
    from test_media_v10 import build, SlowTTS
    from voice_app.media_v10 import V10MediaPipeline
    core = build(tmp_path)
    core.settings.tts_buffer_complete_units = False
    delivered = threading.Event()
    class TTS(SlowTTS):
        def stream_native_pcm(self, *args, **kwargs):
            iterator = super().stream_native_pcm(*args, **kwargs)
            yield next(iterator)
            assert delivered.wait(2), "first PCM must reach the consumer before synthesis finishes"
            yield from iterator
    core.tts = TTS(tmp_path)
    events = []
    for event in V10MediaPipeline(core).stream_turn(query_text="Xin chào"):
        events.append(event)
        if event.get("type") == "pcm":
            delivered.set()
    assert delivered.is_set() and any(e.get("type") == "done" for e in events)
