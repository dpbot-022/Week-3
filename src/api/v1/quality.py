import os
import glob
import json
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from src.db.session import get_db
from src.db.models import WrongAnswerReport, User
from src.auth.deps import require_permission
from src.core.rbac import PERM_READ_QUALITY, PERM_READ_RAG
from src.core.audit import audit_service
from src.core.config import BASE_DIR

router = APIRouter(prefix="/quality", tags=["Quality & Evaluation"])

class WrongAnswerSubmitRequest(BaseModel):
    query: str
    answer: str
    citations: Optional[List[Dict[str, Any]]] = None
    reason: str

@router.get("/reports")
def get_quality_reports(
    current_user: User = Depends(require_permission(PERM_READ_QUALITY))
):
    """Returns the latest evaluation and ablation report read directly from reports/."""
    reports_dir = str(BASE_DIR / "reports")
    os.makedirs(reports_dir, exist_ok=True)
    report_files = sorted(glob.glob(f"{reports_dir}/eval_*.json"), reverse=True)

    latest_report = None
    if report_files:
        try:
            with open(report_files[0], "r") as f:
                latest_report = json.load(f)
        except Exception:
            latest_report = None

    # Load calibration file if present
    calibration_file = str(BASE_DIR / "data" / "calibration.json")
    calibration = {}
    if os.path.exists(calibration_file):
        try:
            with open(calibration_file, "r") as f:
                calibration = json.load(f)
        except Exception:
            pass

    return {
        "available_reports": [os.path.basename(f) for f in report_files],
        "latest_report": latest_report,
        "calibration": calibration
    }

@router.post("/report-wrong-answer")
def report_wrong_answer(
    payload: WrongAnswerSubmitRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission(PERM_READ_RAG))
):
    """Submits a user feedback report for an incorrect or hallucinated answer."""
    report = WrongAnswerReport(
        user_email=current_user.email,
        query=payload.query,
        answer=payload.answer,
        citations_json=json.dumps(payload.citations or []),
        reason=payload.reason,
        status="open"
    )
    db.add(report)
    db.commit()
    db.refresh(report)

    audit_service.log(
        user_email=current_user.email,
        role=current_user.role,
        action="quality:report_wrong_answer",
        resource=f"report:{report.id}",
        details={"reason": payload.reason[:100]},
        db=db
    )

    return {"message": "Thank you. Your feedback has been recorded for compliance review.", "report_id": report.id}

@router.get("/wrong-answers")
def list_wrong_answers(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission(PERM_READ_QUALITY))
):
    reports = db.query(WrongAnswerReport).order_by(WrongAnswerReport.timestamp.desc()).all()
    return [r.to_dict() for r in reports]
