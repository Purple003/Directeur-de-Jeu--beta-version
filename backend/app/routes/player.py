from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Player
from ..schemas import (
    ApiResponse,
    PlayerCreate,
    PlayerCreateResponse,
    PlayerProfile,
    PlayerUpdateRequest,
    PlayerUpdateResponse,
    SubmitScoreRequest,
    SubmitScoreResponse,
)
from ..services.adaptation_service import AdaptationServiceError, submit_score_and_recommend
from ..utils.api_response import ok

router = APIRouter(prefix="/player", tags=["Player"])


@router.post(
    "/create",
    response_model=ApiResponse[PlayerCreateResponse],
    status_code=status.HTTP_201_CREATED,
)
def create_player(payload: PlayerCreate, db: Session = Depends(get_db)):
    try:
        player = Player(
            name=payload.name.strip(),
            age=payload.age,
            school_level=payload.school_level.strip() if payload.school_level else None,
            experience_level=payload.experience_level.strip() if payload.experience_level else None,
        )
        db.add(player)
        db.commit()
        db.refresh(player)
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(status_code=500, detail="Unable to create player right now.")

    return ok(
        PlayerCreateResponse(message="Player created successfully", player_id=player.id).model_dump()
    )


@router.get("/{player_id}", response_model=ApiResponse[PlayerProfile])
def get_player(player_id: int, db: Session = Depends(get_db)):
    player = db.query(Player).filter(Player.id == player_id).first()
    if not player:
        raise HTTPException(status_code=404, detail="Player not found.")
    return ok(
        PlayerProfile(
            id=player.id,
            name=player.name,
            age=player.age,
            school_level=player.school_level,
            experience_level=player.experience_level,
            game_level=int(getattr(player, "game_level", 1) or 1),
            xp=int(getattr(player, "xp", 0) or 0),
            stars=int(getattr(player, "stars", 0) or 0),
        ).model_dump()
    )


@router.put("/update", response_model=ApiResponse[PlayerUpdateResponse])
def update_player(payload: PlayerUpdateRequest, db: Session = Depends(get_db)):
    player = db.query(Player).filter(Player.id == payload.player_id).first()
    if not player:
        raise HTTPException(status_code=404, detail="Player not found.")

    try:
        if payload.name is not None:
            player.name = payload.name.strip()
        if payload.age is not None:
            player.age = payload.age
        if payload.school_level is not None:
            player.school_level = payload.school_level.strip() if payload.school_level else None
        if payload.experience_level is not None:
            player.experience_level = payload.experience_level.strip() if payload.experience_level else None
        db.commit()
        db.refresh(player)
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(status_code=500, detail="Unable to update player right now.")

    return ok(
        PlayerUpdateResponse(
            message="Player updated successfully",
            player=PlayerProfile(
                id=player.id,
                name=player.name,
                age=player.age,
                school_level=player.school_level,
                experience_level=player.experience_level,
                game_level=int(getattr(player, "game_level", 1) or 1),
                xp=int(getattr(player, "xp", 0) or 0),
                stars=int(getattr(player, "stars", 0) or 0),
            ),
        ).model_dump()
    )


@router.post(
    "/submit-score",
    response_model=ApiResponse[SubmitScoreResponse],
    status_code=status.HTTP_201_CREATED,
)
def submit_score(payload: SubmitScoreRequest, db: Session = Depends(get_db)):
    try:
        progress_id, recommended = submit_score_and_recommend(db, payload)
    except AdaptationServiceError:
        raise HTTPException(status_code=500, detail="Unable to save progress right now.")

    return ok(
        SubmitScoreResponse(
            message="Progress saved successfully",
            recommended_difficulty=recommended,
            progress_id=progress_id,
        ).model_dump()
    )
