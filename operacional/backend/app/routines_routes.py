"""Validated API for weekly routines, status calendar, Instagram and training metadata."""
from datetime import date, datetime
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Path, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.auth import current_user
from app.db import get_db
from app.models import User
from app.operations_service import OperationError
from app.routines_service import RoutinesService

router=APIRouter(prefix="/api/v1/routines",tags=["routines"])


class Strict(BaseModel):
    model_config=ConfigDict(extra="forbid")


class TaskInput(Strict):
    reference:date
    title:str=Field(min_length=3,max_length=100)
    details:str=Field(default="",max_length=350)
    frequency:str=Field(pattern=r"^(weekly|once)$")
    day:int=Field(ge=0,le=6)


class VerifyInput(Strict):
    reference:date
    done:bool


class GoalInput(Strict):
    reference:date
    goal:int=Field(ge=1,le=9999)
    confirmed:bool


class WhatsAppInput(Strict):
    product_code:str=Field(min_length=1,max_length=55)
    category:str=Field(default="",max_length=120)
    note:str=Field(default="",max_length=450)
    status:str=Field(pattern=r"^(planejado|arte_pronta|publicado)$")
    expected_revision:int=Field(ge=0)


class DayOffInput(Strict):
    off:bool
    reason:str=Field(default="",max_length=150)


class InstagramInput(Strict):
    planned:int=Field(ge=0,le=500)
    completed:int=Field(ge=0,le=500)
    expected_revision:int=Field(ge=0)


class TrainingInput(Strict):
    participant_id:UUID
    procedure:str=Field(min_length=1,max_length=40)
    version:str=Field(min_length=1,max_length=45)
    title:str=Field(default="",max_length=140)
    instructor:str=Field(min_length=1,max_length=90)
    happened_on:datetime
    step:str=Field(pattern=r"^(participou|pratica)$")
    note:str=Field(default="",max_length=350)


def service(user:User=Depends(current_user),db:Session=Depends(get_db))->RoutinesService:
    return RoutinesService(db,user)


def checked(fn):
    try:return fn()
    except OperationError as err:
        raise HTTPException(status_code=err.status_code,detail=err.message) from err


@router.get("/checklist/{store_code}/{reference}")
def checklist(store_code:str,reference:date,svc:RoutinesService=Depends(service))->dict:
    return checked(lambda:svc.week(store_code,reference))


@router.post("/checklist/{store_code}/tasks",status_code=201)
def add_task(store_code:str,body:TaskInput,svc:RoutinesService=Depends(service))->dict:
    return checked(lambda:svc.create_weekly_task(
        store_code,body.reference,body.title,body.details,body.frequency,body.day
    ))


@router.put("/checklist/{store_code}/tasks/{task_id}")
def edit_task(store_code:str,task_id:UUID,body:TaskInput,
              svc:RoutinesService=Depends(service))->dict:
    return checked(lambda:svc.revise_task(
        store_code,task_id,body.reference,body.title,body.details,body.frequency,body.day
    ))


@router.put("/checklist/{store_code}/tasks/{task_id}/check")
def check_task(store_code:str,task_id:UUID,body:VerifyInput,
               svc:RoutinesService=Depends(service))->dict:
    return checked(lambda:svc.verify_task(store_code,task_id,body.reference,body.done))


@router.put("/checklist/{store_code}/calls-goal")
def change_goal(store_code:str,body:GoalInput,svc:RoutinesService=Depends(service))->dict:
    return checked(lambda:svc.weekly_goal(store_code,body.reference,body.goal,body.confirmed))


@router.get("/whatsapp/{year}/{month}")
def whatsapp(year:int=Path(ge=2020,le=2100),
             month:int=Path(ge=1,le=12),svc:RoutinesService=Depends(service))->dict:
    return checked(lambda:svc.marketing(year,month))


@router.put("/whatsapp/{post_date}")
def save_post(post_date:date,body:WhatsAppInput,svc:RoutinesService=Depends(service))->dict:
    return checked(lambda:svc.save_marketing(
        post_date,body.product_code,body.category,body.note,
        body.status,body.expected_revision
    ))


class DeletePost(Strict):
    expected_revision:int=Field(ge=1)


@router.delete("/whatsapp/{post_date}")
def delete_post(post_date:date,body:DeletePost,svc:RoutinesService=Depends(service))->dict:
    return checked(lambda:svc.delete_marketing(post_date,body.expected_revision))


@router.put("/whatsapp/{post_date}/day-off")
def day_off(post_date:date,body:DayOffInput,
            svc:RoutinesService=Depends(service))->dict:
    return checked(lambda:svc.set_day_off(post_date,body.off,body.reason))


@router.get("/instagram/{year}/{month}")
def instagram(year:int=Path(ge=2020,le=2100),
              month:int=Path(ge=1,le=12),svc:RoutinesService=Depends(service))->dict:
    return checked(lambda:svc.instagram(year,month))


@router.put("/instagram/{store_code}/{year}/{month}")
def save_instagram(store_code:str,body:InstagramInput,
                   year:int=Path(ge=2020,le=2100),
                   month:int=Path(ge=1,le=12),
                   svc:RoutinesService=Depends(service))->dict:
    return checked(lambda:svc.save_instagram(
        store_code,year,month,body.planned,body.completed,body.expected_revision
    ))


@router.get("/trainings/{store_code}")
def trainings(store_code:str,limit:int=Query(100,ge=1,le=500),
              svc:RoutinesService=Depends(service))->list[dict]:
    return checked(lambda:svc.training(store_code,limit))


@router.post("/trainings/{store_code}",status_code=201)
def add_training(store_code:str,body:TrainingInput,
                 svc:RoutinesService=Depends(service))->dict:
    return checked(lambda:svc.add_training(
        store_code,body.participant_id,body.procedure,body.version,
        body.title,body.instructor,body.happened_on,body.step,body.note
    ))
