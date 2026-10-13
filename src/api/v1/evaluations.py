from fastapi import APIRouter, Depends
from src.schemas.models import BenchmarkReport
from src.api.deps import get_benchmark_runner, get_current_user
from src.db.models import User

router = APIRouter(prefix="/evaluations", tags=["Automated Evaluations & Benchmarks"])

@router.post("/benchmark", response_model=BenchmarkReport)
async def run_benchmark(
    benchmark_runner=Depends(get_benchmark_runner),
    current_user: User = Depends(get_current_user)
):
    """Runs automated RAG evaluation matrix across all retrieval modes and returns benchmark report."""
    return benchmark_runner.run_benchmark()
