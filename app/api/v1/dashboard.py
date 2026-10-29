"""Dashboard page and bounded LLM analysis endpoint."""
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.core.llm import LLMService, get_llm_service
from app.services.graph_service import GraphService, get_graph_service

router = APIRouter(tags=["dashboard"])
DASHBOARD_FILE = Path(__file__).resolve().parents[2] / "static" / "dashboard.html"


class AnalyzeRequest(BaseModel):
    drug_name: str = Field(min_length=1, max_length=120)


@router.get("/dashboard", include_in_schema=False)
async def dashboard_page() -> FileResponse:
    return FileResponse(DASHBOARD_FILE)


@router.post("/dashboard/analyze")
async def analyze_changes(
    request: AnalyzeRequest,
    graph: GraphService = Depends(get_graph_service),
    llm: LLMService = Depends(get_llm_service),
) -> dict:
    """Summarize bounded, already-computed diffs; never send full label histories."""
    try:
        result = await graph.get_drug_change_timeline(drug_name=request.drug_name)
        payload = result.model_dump() if hasattr(result, "model_dump") else result.dict()
        compact = {
            "drug_name": payload.get("drug_name", request.drug_name),
            "total_versions": payload.get("total_versions"),
            "total_transitions": payload.get("total_transitions"),
            "total_changes": payload.get("total_changes"),
            "timeline": [],
        }
        remaining_chars = 18000
        for transition in payload.get("timeline", []):
            row = {
                "from_version_number": transition.get("from_version_number"),
                "to_version_number": transition.get("to_version_number"),
                "effective_date": transition.get("effective_date"),
                "changes": [],
            }
            for change in transition.get("changes", []):
                if len(row["changes"]) >= 20 or remaining_chars <= 0:
                    break
                item = {
                    "section_name": change.get("section_name"),
                    "change_type": change.get("change_type"),
                    "summary": (change.get("summary") or "")[:500],
                    "added_lines": change.get("added_lines"),
                    "removed_lines": change.get("removed_lines"),
                    "diff_excerpt": (change.get("diff") or "")[: min(700, remaining_chars)],
                }
                remaining_chars -= len(item["diff_excerpt"])
                row["changes"].append(item)
            compact["timeline"].append(row)
            if remaining_chars <= 0:
                break

        prompt = (
            "Analyze these computed pharmaceutical label diffs. Report: key observed changes; "
            "potentially safety-relevant changes with section and version references; additions, "
            "removals, and modifications; and data limitations. Clearly separate observations "
            "from interpretation. Do not invent facts or provide patient-specific advice. "
            "If data was truncated, say so. Keep the answer under 350 words.\n\nDATA:\n"
            + __import__("json").dumps(compact, ensure_ascii=False)
        )
        answer = await llm.complete(
            prompt=prompt,
            system_prompt="You are a careful regulatory label-change analyst. Use only supplied data.",
            temperature=0,
            max_tokens=500,
        )
        return {"drug_name": request.drug_name, "analysis": answer, "input_chars": len(prompt), "truncated": remaining_chars <= 0}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Label analysis failed: {exc}") from exc
