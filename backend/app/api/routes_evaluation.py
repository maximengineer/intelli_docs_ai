from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from app.evaluation.service import get_evaluation_service

router = APIRouter(prefix="/evaluation", tags=["evaluation"])


@router.post("/run", status_code=status.HTTP_202_ACCEPTED)
def run_evaluation() -> dict[str, object]:
    """Start an offline evaluation run asynchronously.

    The run is forced offline (deterministic, no paid LLM calls) and its result
    is retrieved from ``GET /evaluation/{evaluation_id}``.
    """
    run = get_evaluation_service().submit()
    return {"evaluation_id": run.evaluation_id, "status": run.status}


@router.get("/{evaluation_id}")
def get_evaluation(evaluation_id: str) -> dict[str, object]:
    run = get_evaluation_service().get(evaluation_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Evaluation not found.")
    return {
        "evaluation_id": run.evaluation_id,
        "status": run.status,
        "result": run.result,
        "error": run.error,
    }
