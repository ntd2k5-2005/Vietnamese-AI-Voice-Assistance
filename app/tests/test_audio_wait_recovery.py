import threading
import time

from voice_app.web import AudioPacket, TurnManager, TurnSession


def test_audio_wait_timeout_releases_producer_lock_and_can_resume():
    session = TurnSession("test", "conversation", 1, time.time())
    result = []
    reader = threading.Thread(target=lambda: result.append(TurnManager.next_audio(session, 0, .01)), daemon=True)
    reader.start()
    reader.join(.5)
    assert not reader.is_alive(), "timeout must return rather than spin holding audio_condition"
    assert result == [None]
    assert session.audio_condition.acquire(timeout=.1)
    packet = AudioPacket(b"\x00\x00", {"chunk_index": 1})
    try:
        session.audio_log.append(packet)
        session.audio_condition.notify_all()
    finally:
        session.audio_condition.release()
    assert TurnManager.next_audio(session, 0, .01) is packet


def test_finished_audio_returns_without_waiting_for_more_pcm():
    session = TurnSession("test", "conversation", 1, time.time())
    session.audio_finished = True
    assert TurnManager.next_audio(session, 0, 10) is None


def test_complete_sentence_reaches_tts_before_llm_finishes(tmp_path):
    from test_media_v10 import build, SlowTTS, FastLLM
    from voice_app.media_v10 import V10MediaPipeline

    tts_started = threading.Event()
    class Speech(SlowTTS):
        def stream_native_pcm(self, *args, **kwargs):
            tts_started.set()
            yield from super().stream_native_pcm(*args, **kwargs)
    class PausedLLM(FastLLM):
        def chat_stream(self, *args, **kwargs):
            yield {"type": "delta", "content": "Đây là câu đầu tiên đã hoàn chỉnh. "}
            assert tts_started.wait(1), "a complete sentence must not wait for final LLM output"
            yield {"type": "delta", "content": "Và đây là câu tiếp theo."}
            yield {"type": "done"}
    core = build(tmp_path)
    core.llm = PausedLLM()
    core.tts = Speech(tmp_path)
    events = list(V10MediaPipeline(core).stream_turn(query_text="Xin chào"))
    assert len(core.tts.calls) == 2
    assert any(e["type"] == "done" for e in events)


def test_audio_websocket_keeps_waiting_after_timeout_instead_of_ending(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient
    import voice_app.web as web
    from test_media_v10 import build

    core = build(tmp_path)
    monkeypatch.setattr(web, "VoiceOrchestrator", lambda settings: core)
    app = web.create_app()
    manager = app.state.turn_manager
    session = TurnSession("late", "conversation", 1, time.time())
    session.finished.set()  # No background worker/history mutation in this test.
    manager._turns["late"] = session
    calls = []
    def next_audio(session, cursor, timeout):
        calls.append(cursor)
        if len(calls) == 1:
            return None
        if len(calls) == 2:
            return AudioPacket(b"\x00\x00", {"chunk_index": 1, "frame_count": 1})
        session.audio_finished = True
        return None
    monkeypatch.setattr(manager, "next_audio", next_audio)
    with TestClient(app) as client:
        with client.websocket_connect("/ws/turn/late/audio") as socket:
            assert socket.receive_json()["type"] == "keepalive"
            assert socket.receive_bytes().startswith(b"V10P")
            assert socket.receive_json()["type"] == "end"


def test_document_list_hides_only_deleted_or_exact_demo_sources(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient
    import voice_app.web as web
    from test_media_v10 import build
    core = build(tmp_path)
    documents = [
        {"document_id": "colab-smoke-123", "filename": "smoke-source.txt", "status": "active"},
        {"document_id": "old", "status": "deleted"},
        {"document_id": "colab-smoke-law", "filename": "law.docx", "status": "active"},
    ]
    core.rag.list_documents = lambda: documents
    monkeypatch.setattr(web, "VoiceOrchestrator", lambda settings: core)
    with TestClient(web.create_app()) as client:
        assert client.get("/api/knowledge/documents").json() == [documents[-1]]
