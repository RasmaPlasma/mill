"""LLM model registry routes — /v1/models."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from db.engine import get_db
from db.models import LLMModel
from schemas.models import LLMModelCreate, LLMModelListResponse, LLMModelResponse, LLMModelUpdate

router = APIRouter(prefix="/v1/models", tags=["Models"])


class _BulkArchiveRequest(BaseModel):
    ids: list[str]


def _to_response(model: LLMModel) -> LLMModelResponse:
    return LLMModelResponse(
        id=model.id,
        display_name=model.display_name,
        provider=model.provider,
        provider_model=model.provider_model,
        description=model.description,
        created_at=model.created_at,
        updated_at=model.updated_at,
        archived_at=model.archived_at,
    )


@router.post("", response_model=LLMModelResponse, status_code=201)
async def create_llm_model(
    body: LLMModelCreate,
    db: AsyncSession = Depends(get_db),
):
    model = LLMModel(
        display_name=body.display_name,
        provider=body.provider,
        provider_model=body.provider_model,
        description=body.description,
    )
    db.add(model)
    await db.flush()
    await db.refresh(model)
    await db.commit()
    return _to_response(model)


@router.get("", response_model=LLMModelListResponse)
async def list_llm_models(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(LLMModel)
        .where(LLMModel.archived_at.is_(None))
        .order_by(LLMModel.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    result = await db.execute(stmt)
    models = result.scalars().all()

    count_stmt = select(func.count()).select_from(LLMModel).where(LLMModel.archived_at.is_(None))
    count = (await db.execute(count_stmt)).scalar_one()

    return LLMModelListResponse(items=[_to_response(m) for m in models], count=count)


@router.get("/{model_id}", response_model=LLMModelResponse)
async def get_llm_model(
    model_id: str,
    db: AsyncSession = Depends(get_db),
):
    stmt = select(LLMModel).where(LLMModel.id == model_id, LLMModel.archived_at.is_(None))
    result = await db.execute(stmt)
    model = result.scalar_one_or_none()
    if model is None:
        raise HTTPException(status_code=404, detail="Model not found")
    return _to_response(model)


@router.patch("/{model_id}", response_model=LLMModelResponse)
async def update_llm_model(
    model_id: str,
    body: LLMModelUpdate,
    db: AsyncSession = Depends(get_db),
):
    stmt = select(LLMModel).where(LLMModel.id == model_id, LLMModel.archived_at.is_(None))
    result = await db.execute(stmt)
    model = result.scalar_one_or_none()
    if model is None:
        raise HTTPException(status_code=404, detail="Model not found")

    update_data = body.model_dump(exclude_unset=True)
    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update")

    for field, value in update_data.items():
        setattr(model, field, value)

    await db.flush()
    await db.refresh(model)
    await db.commit()
    return _to_response(model)


@router.post("/{model_id}/archive", status_code=204)
async def archive_llm_model(
    model_id: str,
    db: AsyncSession = Depends(get_db),
):
    stmt = select(LLMModel).where(LLMModel.id == model_id, LLMModel.archived_at.is_(None))
    result = await db.execute(stmt)
    model = result.scalar_one_or_none()
    if model is None:
        raise HTTPException(status_code=404, detail="Model not found")

    model.archived_at = datetime.now(timezone.utc)
    await db.flush()
    await db.commit()


@router.post("/archive", status_code=204)
async def bulk_archive_models(
    body: _BulkArchiveRequest,
    db: AsyncSession = Depends(get_db),
):
    if not body.ids:
        raise HTTPException(status_code=400, detail="No IDs provided")
    stmt = (
        update(LLMModel)
        .where(LLMModel.id.in_(body.ids), LLMModel.archived_at.is_(None))
        .values(archived_at=datetime.now(timezone.utc))
        .execution_options(synchronize_session="fetch")
    )
    result = await db.execute(stmt)
    await db.commit()
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="No models found to archive")
    return None
