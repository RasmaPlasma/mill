"""Agent CRUD routes — /v1/agents."""

from datetime import datetime, timezone

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, func, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from db.engine import get_db
from db.models import Agent, LLMModel
from schemas.agents import AgentCreate, AgentListResponse, AgentResponse, AgentUpdate

router = APIRouter(prefix="/v1/agents", tags=["Agents"])


class _BulkArchiveRequest(BaseModel):
    ids: list[str]


def _to_response(agent: Agent) -> AgentResponse:
    return AgentResponse(
        id=agent.id,
        name=agent.name,
        model_id=agent.model_id,
        model=agent.llm_model.display_name if agent.llm_model else None,
        system_prompt=agent.system_prompt,
        tools=agent.tools or [],
        mcp_servers=agent.mcp_servers or [],
        description=agent.description,
        metadata=agent.metadata_ or {},
        version=agent.version,
        created_at=agent.created_at,
        updated_at=agent.updated_at,
        archived_at=agent.archived_at,
    )


@router.post("", response_model=AgentResponse, status_code=201)
async def create_agent(
    body: AgentCreate,
    db: AsyncSession = Depends(get_db),
):
    # Validate model_id exists if provided
    if body.model_id:
        model_stmt = select(LLMModel).where(
            LLMModel.id == body.model_id, LLMModel.archived_at.is_(None)
        )
        model_result = await db.execute(model_stmt)
        if model_result.scalar_one_or_none() is None:
            raise HTTPException(status_code=400, detail="Model not found or archived")

    agent = Agent(
        name=body.name,
        model_id=body.model_id,
        system_prompt=body.system_prompt,
        tools=body.tools,
        mcp_servers=body.mcp_servers,
        description=body.description,
        metadata_=body.metadata,
    )
    db.add(agent)
    await db.flush()
    await db.refresh(agent)
    await db.commit()
    return _to_response(agent)


@router.get("", response_model=AgentListResponse)
async def list_agents(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(Agent)
        .options(joinedload(Agent.llm_model))
        .where(Agent.archived_at.is_(None))
        .order_by(Agent.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    result = await db.execute(stmt)
    agents = result.unique().scalars().all()

    count_stmt = select(func.count()).select_from(Agent).where(Agent.archived_at.is_(None))
    count = (await db.execute(count_stmt)).scalar_one()

    return AgentListResponse(items=[_to_response(a) for a in agents], count=count)


@router.get("/{agent_id}", response_model=AgentResponse)
async def get_agent(
    agent_id: str,
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(Agent)
        .options(joinedload(Agent.llm_model))
        .where(Agent.id == agent_id, Agent.archived_at.is_(None))
    )
    result = await db.execute(stmt)
    agent = result.unique().scalar_one_or_none()
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    return _to_response(agent)


@router.patch("/{agent_id}", response_model=AgentResponse)
async def update_agent(
    agent_id: str,
    body: AgentUpdate,
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Agent).where(Agent.id == agent_id, Agent.archived_at.is_(None))
    result = await db.execute(stmt)
    agent = result.scalar_one_or_none()
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found")

    update_data = body.model_dump(exclude_unset=True)
    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update")

    # Validate model_id exists if provided
    if "model_id" in update_data and update_data["model_id"]:
        model_stmt = select(LLMModel).where(
            LLMModel.id == update_data["model_id"], LLMModel.archived_at.is_(None)
        )
        model_result = await db.execute(model_stmt)
        if model_result.scalar_one_or_none() is None:
            raise HTTPException(status_code=400, detail="Model not found or archived")

    # Map 'metadata' key to 'metadata_' column attribute
    if "metadata" in update_data:
        update_data["metadata_"] = update_data.pop("metadata")

    # Prevent storing null for list fields — coerce None to []
    for list_field in ("tools", "mcp_servers"):
        if list_field in update_data and update_data[list_field] is None:
            update_data[list_field] = []

    for field, value in update_data.items():
        setattr(agent, field, value)

    agent.version += 1
    await db.flush()
    await db.refresh(agent)
    await db.commit()
    return _to_response(agent)


@router.post("/{agent_id}/archive", status_code=204)
async def archive_agent(
    agent_id: str,
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Agent).where(Agent.id == agent_id, Agent.archived_at.is_(None))
    result = await db.execute(stmt)
    agent = result.scalar_one_or_none()
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found")

    agent.archived_at = datetime.now(timezone.utc)
    await db.flush()
    await db.commit()


@router.post("/archive", status_code=204)
async def bulk_archive_agents(
    body: _BulkArchiveRequest,
    db: AsyncSession = Depends(get_db),
):
    if not body.ids:
        raise HTTPException(status_code=400, detail="No IDs provided")
    stmt = (
        update(Agent)
        .where(Agent.id.in_(body.ids), Agent.archived_at.is_(None))
        .values(archived_at=datetime.now(timezone.utc))
        .execution_options(synchronize_session="fetch")
    )
    result = await db.execute(stmt)
    await db.commit()
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="No agents found to archive")
    return None
