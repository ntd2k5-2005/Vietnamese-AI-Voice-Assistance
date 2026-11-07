"""Offline tests: never install packages, download models or start services."""
import hashlib
import ast
import importlib.util
import json
from pathlib import Path
from unittest.mock import Mock

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("cloud_runtime", ROOT / "scripts/cloud_notebook_runtime.py")
runtime = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runtime)


def bare_demo(tmp_path):
    demo = object.__new__(runtime.CloudDemo)
    demo.storage = tmp_path
    demo.state = {"stages": {}, "processes": {}, "run_id": "test-owner"}
    demo.processes = {}
    demo.save = Mock()
    (tmp_path / "downloads").mkdir()
    return demo


@pytest.mark.parametrize("gpu,index", [("Tesla P100", "cu126"), ("Tesla T4", "cu126"),
                                        ("NVIDIA A100", "cu126"), ("NVIDIA B200", "cu128"),
                                        ("GeForce RTX 5090", "cu128")])
def test_cuda_policy(gpu, index):
    assert runtime.choose_cuda_index(gpu) == index


def test_tunnel_uses_latest_url_and_rejects_non_tunnel_hosts():
    assert runtime.find_tunnel_url("https://api.trycloudflare.com https://www.trycloudflare.com") is None
    assert runtime.find_tunnel_url("https://fake.trycloudflare.com.evil.org") is None
    assert runtime.find_tunnel_url("https://old-link.trycloudflare.com\nhttps://fresh-link.trycloudflare.com") == "https://fresh-link.trycloudflare.com"


def test_windows_cannot_accidentally_install(monkeypatch):
    monkeypatch.setattr(runtime.platform, "system", lambda: "Windows")
    with pytest.raises(RuntimeError, match="Windows"):
        runtime.CloudDemo()


def test_http_200_is_not_enough_when_upstream_is_unready():
    with pytest.raises(RuntimeError, match="tts"):
        runtime.require_ready({"ready": False, "services": {"tts": {"ready": False, "reachable": True}}})
    runtime.require_ready({"ready": True})


def test_stage_resume_revalidates_and_never_marks_failed_probe_done(tmp_path):
    demo = bare_demo(tmp_path)
    action = Mock()
    demo.stage("install", action, lambda: True)
    demo.stage("install", action, lambda: True)
    assert action.call_count == 1
    with pytest.raises(RuntimeError):
        demo.stage("broken", action, lambda: False)
    assert demo.state["stages"]["broken"] == "FAILED"
    assert demo.state["stages"]["install"] == "DONE"


def test_existing_download_requires_matching_checksum(tmp_path, monkeypatch):
    demo = bare_demo(tmp_path)
    data = b"downloaded-tool"
    monkeypatch.setitem(runtime.ASSETS, "test", ("https://example.test/tool", hashlib.sha256(data).hexdigest()))
    (tmp_path / "downloads/tool").write_bytes(data)
    network = Mock(side_effect=AssertionError("must not download"))
    monkeypatch.setattr(runtime.urllib.request, "urlopen", network)
    assert demo.download("test").read_bytes() == data
    network.assert_not_called()


def test_partial_download_resumes_and_verifies(tmp_path, monkeypatch):
    import io
    demo = bare_demo(tmp_path)
    data = b"complete-tool"
    monkeypatch.setitem(runtime.ASSETS, "test", ("https://example.test/tool", hashlib.sha256(data).hexdigest()))
    (tmp_path / "downloads/tool.part").write_bytes(data[:4])
    response = io.BytesIO(data[4:])
    response.status = 206
    response.headers = {"Content-Range": "bytes 4-12/13"}
    network = Mock(return_value=response)
    monkeypatch.setattr(runtime.urllib.request, "urlopen", network)
    assert demo.download("test").read_bytes() == data
    request = network.call_args.args[0]
    assert request.get_header("Range") == "bytes=4-"
    assert not (tmp_path / "downloads/tool.part").exists()


def test_stop_does_not_touch_unowned_processes(tmp_path, monkeypatch):
    demo = bare_demo(tmp_path)
    demo.state["processes"] = {"ollama": {"pid": 99999}}
    demo.owns = lambda role: False
    kill = Mock()
    monkeypatch.setattr(runtime.os, "killpg", kill, raising=False)
    demo.stop()
    kill.assert_not_called()


def test_tool_downloads_are_pinned():
    for url, digest in runtime.ASSETS.values():
        assert "/latest/" not in url
        assert url.startswith("https://github.com/")
        assert len(digest) == 64 and int(digest, 16)


def llm_demo(tmp_path):
    demo = bare_demo(tmp_path)
    demo.root = tmp_path
    (tmp_path / "config").mkdir()
    (tmp_path / "runtime").mkdir()
    manifest = {"components": {"llm": {"model_id": runtime.OLLAMA_PIN["model_id"],
                 "manifest_digest": runtime.OLLAMA_PIN["manifest_digest"]}}}
    (tmp_path / "config/model_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    demo.manifest = manifest
    demo.run = Mock()
    demo.ollama = "/project/orther/tools/ollama/bin/ollama"
    return demo






def test_matching_model_with_prefix_and_model_field_reuses_download(tmp_path, monkeypatch):
    demo = llm_demo(tmp_path)
    row = {"model": runtime.OLLAMA_PIN["model_id"], "digest": "sha256:" + runtime.OLLAMA_PIN["manifest_digest"]}
    demo.http_json = Mock(return_value={"models": [row]})
    monkeypatch.setattr(runtime.urllib.request, "urlopen", Mock(side_effect=AssertionError("no download needed")))
    demo.ensure_llm()
    demo.run.assert_not_called()
    assert json.loads((tmp_path / "runtime/ollama-model-check.json").read_text())["passed"] is True


@pytest.mark.parametrize("actual", [None, "abc", "z" * 64, "f" * 64])
def test_bad_digest_is_not_accepted(actual):
    assert not runtime.model_matches({"digest": actual}, runtime.OLLAMA_PIN["manifest_digest"])


def test_changed_registry_tag_stops_before_expensive_pull(tmp_path, monkeypatch):
    import io
    demo = llm_demo(tmp_path)
    demo.http_json = Mock(return_value={"models": []})
    monkeypatch.setattr(runtime.urllib.request, "urlopen", Mock(return_value=io.BytesIO(b"changed manifest")))
    with pytest.raises(RuntimeError, match="Registry:"):
        demo.ensure_llm()
    demo.run.assert_not_called()
    report = json.loads((tmp_path / "runtime/ollama-model-check.json").read_text())
    assert report["expected_digest"] != report["registry_digest"]


@pytest.mark.parametrize("correct_pull", [True, False])
def test_pull_validates_before_and_after_download(tmp_path, monkeypatch, correct_pull):
    import io
    demo = llm_demo(tmp_path)
    raw = b'{"fixture":"official registry manifest"}'
    expected = hashlib.sha256(raw).hexdigest()
    monkeypatch.setitem(runtime.OLLAMA_PIN, "manifest_digest", expected)
    demo.manifest["components"]["llm"]["manifest_digest"] = expected
    row = {"name": runtime.OLLAMA_PIN["model_id"], "digest": expected if correct_pull else "1" * 64}
    demo.http_json = Mock(side_effect=[{"models": []}, {"models": [row]}])
    monkeypatch.setattr(runtime.urllib.request, "urlopen", Mock(return_value=io.BytesIO(raw)))
    if correct_pull:
        demo.ensure_llm()
    else:
        with pytest.raises(RuntimeError, match="Thực nhận:"):
            demo.ensure_llm()
    demo.run.assert_called_once_with([demo.ollama, "pull", runtime.OLLAMA_PIN["model_id"]], label="pull-llm")
    assert json.loads((tmp_path / "runtime/ollama-model-check.json").read_text())["passed"] is correct_pull


def test_notebook_is_standalone_and_has_no_saved_outputs():
    path = ROOT / "notebooks/CHAY_VIETNAMESE_VOICE_AI_COLAB_KAGGLE.ipynb"
    notebook = json.loads(path.read_text(encoding="utf-8"))
    assert notebook["nbformat"] == 4
    assert path.read_bytes() == (ROOT.parent / path.name).read_bytes()
    assert not any(c["id"] == "source-overlay" for c in notebook["cells"])
    assert len({c["id"] for c in notebook["cells"]}) == len(notebook["cells"])
    for number, cell in enumerate(notebook["cells"]):
        if cell["cell_type"] == "code":
            assert cell["outputs"] == [] and cell["execution_count"] is None
            compile("".join(cell["source"]), f"cell-{number}", "exec")
    helper = next(c for c in notebook["cells"] if c["id"] == "runtime-helper")
    assert "".join(helper["source"]) == (ROOT / "scripts/cloud_notebook_runtime.py").read_text(encoding="utf-8")
    assert "demo.keep_alive" in "".join(notebook["cells"][-1]["source"])
    for cell in notebook["cells"]:
        if cell["cell_type"] == "code" and cell["id"] != "runtime-helper":
            tree = ast.parse("".join(cell["source"]))
            assert not any(isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                           and node.func.attr == "stop" for node in ast.walk(tree))








