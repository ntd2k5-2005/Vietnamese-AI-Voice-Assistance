# Nguồn gốc thành phần

Các thành phần sử dụng các nguồn và revision sau. Thông tin này phục vụ truy xuất nguồn gốc, không thể hiện liên kết tổ chức.

| Module | Upstream | Baseline commit |
|---|---|---|
| STT | https://github.com/YuluWusu/Speech-to-Text-Long | `bab59e7289e8ab0a82f8e33b92dc8d9704c6b9f4` |
| RAG | https://github.com/ntd2k5-2005/rag-service | `0492dca4b493644aab715c19debf97762839638d` |
| LLM | https://github.com/tsuk1shima-cs/LLM-Model | `dafecbec16b5c2b5b025e5f65fca6b115d352ffe` |
| TTS | https://github.com/PhatTran-71/API-TTS | `8fff60262a05d5fb462def6115de8324daca2b37` |
| App/FE | https://github.com/ntd2k5-2005/fe-voice-chatbot | `d13a13b372ad19f1ef61f1de7ef6df49fc879eb8` |

## Môi trường giọng đọc

VieNeu-TTS được ghim theo repository và commit trong `services/tts/runtime.json`, tái lập bằng `uv sync --frozen`. Giữ nguyên thông tin tác giả và giấy phép của các thư viện/model được sử dụng.
