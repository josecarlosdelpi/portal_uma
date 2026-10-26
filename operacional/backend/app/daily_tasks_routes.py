"""Rotas autenticadas das tarefas diárias, separadas do checklist semanal."""
from datetime import date
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.auth import current_user
from app.db import get_db
from app.daily_tasks_service import DailyTaskService
from app.models import User
from app.operations_service import OperationError

router = APIRouter(prefix="/api/v1/daily-tasks", tags=["daily-tasks"])


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TaskNew(Strict):
    date: date
    title: str = Field(min_length=3, max_length=120)
    details: str = Field(default="", max_length=400)
    priority: Literal["baixa", "normal", "alta"] = "normal"
    assignee_id: UUID | None = None


class TaskEdit(TaskNew):
    status: Literal["pendente", "em_andamento", "concluida"]
    expected_revision: int = Field(ge=1)


class DeleteTask(Strict):
    expected_revision: int = Field(ge=1)


def service(user: User = Depends(current_user),
            db: Session = Depends(get_db)) -> DailyTaskService:
    return DailyTaskService(db, user)


def checked(fn):
    try:
        return fn()
    except OperationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@router.get("/{store_code}/{day}")
def list_daily(store_code: str, day: date,
               svc: DailyTaskService = Depends(service)) -> dict:
    return checked(lambda: svc.list(store_code, day))


@router.post("/{store_code}", status_code=201)
def add_daily(store_code: str, body: TaskNew,
              svc: DailyTaskService = Depends(service)) -> dict:
    return checked(lambda: svc.create(
        store_code, body.date, body.title, body.details,
        body.priority, body.assignee_id
    ))


@router.put("/{store_code}/{task_id}")
def edit_daily(store_code: str, task_id: UUID, body: TaskEdit,
               svc: DailyTaskService = Depends(service)) -> dict:
    return checked(lambda: svc.update(
        store_code, task_id, day=body.date, title=body.title,
        details=body.details, priority=body.priority, status=body.status,
        assignee_id=body.assignee_id,
        expected_revision=body.expected_revision,
    ))


@router.delete("/{store_code}/{task_id}")
def delete_daily(store_code: str, task_id: UUID, body: DeleteTask,
                 svc: DailyTaskService = Depends(service)) -> dict:
    return checked(lambda: svc.remove(store_code, task_id, body.expected_revision))
