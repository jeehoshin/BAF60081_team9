from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.schemas import UserCreate, UserOut, UserUpdate

router = APIRouter(prefix="/users", tags=["users"])


@router.post("", response_model=UserOut, status_code=201)
def create_user(payload: UserCreate, db: Session = Depends(get_db)):
    taken = db.query(User.user_id).filter(func.lower(User.nickname) == payload.nickname.lower()).first()
    if taken:
        raise HTTPException(status_code=409, detail="이미 사용 중인 닉네임이에요. 다른 닉네임을 써 주세요.")
    user = User(**payload.model_dump())
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.get("", response_model=list[UserOut])
def list_users(db: Session = Depends(get_db)):
    return db.query(User).order_by(User.user_id.desc()).all()


@router.get("/{user_id}", response_model=UserOut)
def get_user(user_id: int, db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="이용자를 찾을 수 없습니다.")
    return user


@router.patch("/{user_id}", response_model=UserOut)
def update_user(user_id: int, payload: UserUpdate, db: Session = Depends(get_db)):
    """내 정보 수정. 조건이 있는 모임에 참여하려고 연령대·성별을 나중에 채울 때 쓴다.

    같은 user_id를 유지하므로 이미 참여한 모임·메시지는 그대로 남는다.
    """
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="이용자를 찾을 수 없습니다.")

    updates = payload.model_dump(exclude_unset=True)
    for key, value in updates.items():
        if isinstance(value, str):
            value = value.strip()
            # 빈 값·"선택 안 함"은 입력 안 한 것으로 저장
            if value in ("", "선택 안 함"):
                value = None
        if key == "nickname" and value is None:
            raise HTTPException(status_code=400, detail="닉네임을 입력해 주세요.")
        setattr(user, key, value)

    db.commit()
    db.refresh(user)
    return user
