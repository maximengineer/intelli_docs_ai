from app.observability.costs import TokenUsage
from app.rag.reranker import LexicalReranker
from app.rag.retriever import RetrievalResult, Retriever
from app.rag.schemas import QARequest, RetrievedChunk
from app.rag.service import QAService


class FakeRetriever:
    def __init__(
        self,
        candidates: list[RetrievedChunk],
        context: list[RetrievedChunk] | None = None,
    ):
        self.candidates = candidates
        self.context = candidates if context is None else context

    def retrieve(self, request: QARequest) -> RetrievalResult:
        return RetrievalResult(candidates=self.candidates, context=self.context)


class FakeLLM:
    def __init__(self, draft: str) -> None:
        self.draft = draft
        self._usage: TokenUsage | None = None

    def complete(self, prompt: str, **_: object) -> str:
        del prompt
        self._usage = TokenUsage(input_tokens=20, output_tokens=5)
        return self.draft

    def pop_usage(self) -> TokenUsage | None:
        usage = self._usage
        self._usage = None
        return usage


class RecordingDocumentService:
    def __init__(self, chunks: list[RetrievedChunk]) -> None:
        self.chunks = chunks
        self.last_document_ids: list[str] | None = None

    def search(
        self,
        query: str,
        top_k: int,
        document_ids: list[str] | None = None,
    ) -> list[RetrievedChunk]:
        del query, top_k
        self.last_document_ids = document_ids
        return self.chunks


def _retrieved_chunk(
    *,
    chunk_id: str = "chunk_1",
    document_id: str = "doc_1",
    text: str = "Total Amount: EUR 12,450.00",
    score: float = 0.9,
) -> RetrievedChunk:
    return RetrievedChunk(
        document_id=document_id,
        filename=f"{document_id}.txt",
        page_number=1,
        section_title="Invoice",
        chunk_id=chunk_id,
        text=text,
        score=score,
    )


def test_qa_rejects_llm_answer_without_citations() -> None:
    service = QAService(
        FakeRetriever([_retrieved_chunk()]),
        llm_client=FakeLLM("The total amount is EUR 12,450."),
    )

    response = service.answer(QARequest(question="What is the total amount?"))

    assert response.status == "insufficient_information"
    assert response.sources == []
    assert response.metrics is not None
    assert response.metrics.support_check_reason == "citation_mapping_failed"


def test_qa_rejects_low_relevance_context_before_generation() -> None:
    service = QAService(
        FakeRetriever([_retrieved_chunk(score=0.01)]),
        llm_client=FakeLLM('The total amount is EUR 12,450. <cite index="0">'),
    )

    response = service.answer(QARequest(question="What is the total amount?"))

    assert response.status == "insufficient_information"
    assert response.sources == []
    assert response.metrics is not None
    assert response.metrics.support_check_reason == "relevance_below_threshold"


def test_lexical_reranker_can_promote_lower_vector_score_candidate() -> None:
    unrelated_high_score = _retrieved_chunk(
        chunk_id="chunk_high",
        text="Remote work policy allows three days per week.",
        score=0.9,
    )
    relevant_lower_score = _retrieved_chunk(
        chunk_id="chunk_relevant",
        text="Invoice total amount is EUR 12,450.",
        score=0.7,
    )

    reranked = LexicalReranker().rerank(
        "invoice amount due",
        [unrelated_high_score, relevant_lower_score],
        top_k=2,
    )

    assert [chunk.chunk_id for chunk in reranked] == ["chunk_relevant", "chunk_high"]
    assert reranked[0].rerank_score is not None


def test_retriever_passes_document_id_filter_to_document_service() -> None:
    document_service = RecordingDocumentService([_retrieved_chunk(document_id="doc_a")])
    retriever = Retriever(document_service)  # type: ignore[arg-type]

    retriever.retrieve(QARequest(question="What is the total amount?", document_ids=["doc_a"]))

    assert document_service.last_document_ids == ["doc_a"]
