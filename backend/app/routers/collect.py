import hmac

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy.orm import Session

from app.collectors import CollectOptions, collect
from app.config import get_settings
from app.database import get_db

router = APIRouter(prefix="/collect", tags=["collect"])


@router.post(
    "",
    summary="공공 API 행사 수집 (KOPIS 공연 · 한국관광공사 축제·행사 · 한국문화정보원 전시)",
    description=(
        "KOPIS, TourAPI, 한국문화정보원에서 서울·대전 행사를 받아 activities에 저장한다. 같은 행사는 다시 받아도 "
        "새로 만들지 않고 고쳐 쓴다. 인증키는 Render 환경변수(KOPIS_API_KEY, TOUR_API_KEY, CULTURE_API_KEY)에서 읽는다.\n\n"
        "아무나 누르지 못하게 `x-collect-token`에 Render 환경변수 COLLECT_TOKEN 값을 넣어야 실행된다. "
        "처음에는 dry_run=true로 저장 없이 결과만 확인해 보자. 수십 초 걸릴 수 있다."
    ),
)
def run_collect(
    x_collect_token: str | None = Header(default=None, description="Render 환경변수 COLLECT_TOKEN과 같은 값"),
    sources: str = Query("kopis,tour,culture", description="kopis, tour, culture 중 쉼표로 구분"),
    areas: str = Query("서울,대전", description="서울, 대전 중 쉼표로 구분"),
    days: int = Query(30, ge=1, le=60, description="오늘부터 며칠 뒤까지의 행사"),
    kopis_per_genre: int = Query(6, ge=1, le=30, description="KOPIS 장르(9개)마다 지역별 최대 건수"),
    max_span_days: int = Query(90, ge=0, le=730, description="이보다 긴 장기·상설 행사는 제외 (0 = 제한 없음)"),
    dry_run: bool = Query(False, description="true면 저장하지 않고 수집 결과만 보여준다"),
    db: Session = Depends(get_db),
):
    settings = get_settings()
    if not settings.collect_token:
        raise HTTPException(
            status_code=503,
            detail="COLLECT_TOKEN이 설정되지 않아 수집을 막아 두었어요. Render 환경변수에 COLLECT_TOKEN을 넣고 재배포하세요.",
        )
    if not x_collect_token or not hmac.compare_digest(x_collect_token.encode(), settings.collect_token.encode()):
        raise HTTPException(status_code=401, detail="x-collect-token 값이 COLLECT_TOKEN과 달라요.")
    try:
        opts = CollectOptions(
            sources=sources,
            areas=areas,
            days=days,
            kopis_per_genre=kopis_per_genre,
            max_span_days=max_span_days,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return collect(
        db,
        opts,
        kopis_key=settings.kopis_api_key,
        tour_key=settings.tour_api_key,
        culture_key=settings.culture_api_key,
        dry_run=dry_run,
    )
