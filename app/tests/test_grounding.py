from __future__ import annotations

from voice_app.contracts import RAGContext
from voice_app.grounding import GroundingPolicy, NO_ANSWER_VI, QueryIntent


def context(text: str = "Kho tri thức có hướng dẫn sử dụng sản phẩm."):
    return RAGContext(
        rank=1,
        chunk_id="chunk-1",
        document_id="doc-1",
        text=text,
        score=0.5,
        score_source="dense",
    )


def test_social_query_bypasses_document_answerability():
    decision = GroundingPolicy().decide("Xin chào", [])
    assert decision.intent == QueryIntent.SOCIAL
    assert decision.context_sufficient is True
    assert decision.forced_answer is None
    assert decision.policy == "social-bypass"


def test_factual_query_without_context_has_deterministic_no_answer():
    decision = GroundingPolicy().decide("Kho tri thức hỗ trợ các loại tài liệu nào?", [])
    assert decision.intent == QueryIntent.FACTUAL
    assert decision.context_sufficient is False
    assert decision.forced_answer == NO_ANSWER_VI
    assert decision.policy == "deterministic-no-answer"


def test_context_presence_does_not_pretend_an_uncalibrated_score_cutoff():
    decision = GroundingPolicy().decide("Kho tri thức có nội dung gì?", [context()])
    assert decision.context_sufficient is True
    assert decision.forced_answer is None
    assert decision.policy == "context-present-prompt-grounding"
    assert decision.calibration_status == "NOT_EVALUATED"


def test_social_classifier_is_narrow_and_does_not_bypass_factual_query():
    policy = GroundingPolicy()
    assert policy.intent("Cảm ơn bạn") == QueryIntent.SOCIAL
    assert policy.intent("Xin chào, thời gian xử lý hồ sơ là bao lâu?") == QueryIntent.FACTUAL
