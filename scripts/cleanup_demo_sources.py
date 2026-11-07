"""Remove only known diagnostic documents through the existing RAG lifecycle."""
import argparse
import json
from urllib.parse import quote
from urllib.request import Request, urlopen


def is_demo_source(document):
    identity = str(document.get("document_id") or "")
    filename = document.get("filename")
    return ((identity.startswith("colab-smoke-") and filename == "smoke-source.txt")
            or (identity.startswith("product-smoke-") and filename == "product-smoke.txt"))


def cleanup(base_url, *, apply=False):
    base = base_url.rstrip("/") + "/v1/knowledge/documents"
    with urlopen(base, timeout=15) as response:
        documents = json.load(response)["documents"]
    selected = [doc for doc in documents if is_demo_source(doc) and doc.get("status") != "deleted"]
    for document in selected:
        if apply:
            with urlopen(Request(base + "/" + quote(document["document_id"], safe=""), method="DELETE"), timeout=30) as response:
                result = json.load(response)
                if not result.get("deleted"):
                    raise RuntimeError("Diagnostic document cleanup was not acknowledged")
    return {"matched": len(selected), "deleted": len(selected) if apply else 0, "dry_run": not apply}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--rag-url", default="http://127.0.0.1:8001")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    print(json.dumps(cleanup(args.rag_url, apply=args.apply)))
