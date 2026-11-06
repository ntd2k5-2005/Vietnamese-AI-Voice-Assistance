import ast
from pathlib import Path
import re

from voice_app.config import DEFAULT_SYSTEM_PROMPT
from voice_app.grounding import GroundingPolicy, QueryIntent

APP = Path(__file__).resolve().parents[1]


def test_product_prompt_has_independent_identity():
    assert "Vietnamese Voice AI" in DEFAULT_SYSTEM_PROMPT
    assert "không đại diện" in DEFAULT_SYSTEM_PROMPT
    assert "hu" + "it" not in DEFAULT_SYSTEM_PROMPT.casefold()
    assert "công" + " thương" not in DEFAULT_SYSTEM_PROMPT.casefold()


def test_product_greeting_is_social_without_a_knowledge_source():
    assert GroundingPolicy().intent("Chào Vietnamese Voice AI") == QueryIntent.SOCIAL
    assert GroundingPolicy().intent("Cảm ơn Vietnamese Voice AI") == QueryIntent.SOCIAL


def test_shipped_product_headers_do_not_show_affiliation_or_release_notes():
    html = (APP / "voice_app/web_assets/index.html").read_text(encoding="utf-8")
    assert "<title>Vietnamese Voice AI</title>" in html
    assert "<h1>Vietnamese Voice AI</h1>" in html
    forbidden = re.compile("|".join(("hu" + "it", "eu" + "reka", "công" + " thương", r"\bv(?:5|6|7|8|9|10)\b", "đã chỉnh sửa")), re.I)
    assert not forbidden.search(html)
    tree = ast.parse((APP / "voice_app/ui.py").read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in {"Blocks", "HTML"}:
            values = [v.value for v in node.args if isinstance(v, ast.Constant) and isinstance(v.value, str)]
            values.extend(k.value.value for k in node.keywords if k.arg == "title" and isinstance(k.value, ast.Constant))
            assert all(not forbidden.search(v) for v in values)
