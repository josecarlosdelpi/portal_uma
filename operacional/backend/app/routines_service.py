"""Checklist, WhatsApp status, Instagram and training metadata; no ERP or public file uploads."""
from datetime import date, datetime, timedelta, time
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models import (
    ContactAttempt, InstagramMonth, TrainingRecord, User,
    WeeklyCallGoal, WeeklyTask, WeeklyTaskCheck, WhatsAppDayOff, WhatsAppPost,
)
from app.operations_service import (
    OperationError, OperationsService, date_time, day_iso, normalize,
)
from app.policy import STORE_CODES

DEFAULT_CALL_GOALS={"JOINVILLE":20,"TUBARAO":12,"ITAJAI":10}
SAO_PAULO=ZoneInfo("America/Sao_Paulo")


def monday(value:date)->date:
    return value-timedelta(days=value.weekday())


def start_of(day:date)->datetime:
    return datetime.combine(day,time.min)


def can_verify(week:date)->bool:
    return monday(week)<=monday(datetime.now(SAO_PAULO).date())


class RoutinesService(OperationsService):
    def week(self, store:str, reference:date)->dict:
        self.require(store,"checklist.view")
        week=monday(reference)
        begin=start_of(week)
        tasks=self.db.scalars(select(WeeklyTask).where(
            WeeklyTask.store_code==store,
            WeeklyTask.start_week<=begin,
            or_(WeeklyTask.end_week.is_(None),WeeklyTask.end_week>=begin),
            or_(WeeklyTask.frequency=="weekly",WeeklyTask.start_week==begin),
        ).order_by(WeeklyTask.scheduled_day,WeeklyTask.title)).all()
        ids=[t.id for t in tasks]
        marks={}
        if ids:
            marks={r.task_id:r for r in self.db.scalars(
                select(WeeklyTaskCheck).where(
                    WeeklyTaskCheck.task_id.in_(ids),
                    WeeklyTaskCheck.week_start==begin,
                )
            ).all()}
        goal=self.db.get(WeeklyCallGoal,{"store_code":store,"week_start":begin})
        count=self.db.scalar(select(func.count(ContactAttempt.id)).where(
            ContactAttempt.store_code==store,
            ContactAttempt.contacted_on>=begin,
            ContactAttempt.contacted_on<begin+timedelta(days=7),
        )) or 0
        target=goal.goal if goal else DEFAULT_CALL_GOALS[store]
        return {
            "store_code":store,"week_start":week.isoformat(),
            "week_end":(week+timedelta(days=6)).isoformat(),
            "items":[{"id":str(t.id),"title":t.title,"details":t.details,
                     "frequency":t.frequency,"day":t.scheduled_day,
                     "done":marks[t.id].done if t.id in marks else False}
                     for t in tasks],
            "calls":{"count":count,"target":target,"reached":count>=target,
                     "confirmed":goal.confirmed if goal else False},
        }

    def create_weekly_task(self,store:str,reference:date,title:str,details:str,
                           frequency:str,day:int)->dict:
        self.require(store,"checklist.edit")
        week=monday(reference)
        title=title.strip()
        if len(title)<3 or frequency not in {"weekly","once"} or not 0<=day<=6:
            raise OperationError(422,"Tarefa inválida")
        task=WeeklyTask(
            id=uuid4(),store_code=store,title=title,details=details,
            frequency=frequency,scheduled_day=day,start_week=start_of(week),
            end_week=None,active=True,created_by=self.actor.id,
        )
        self.db.add(task)
        self.audit("checklist.task.created","weekly_task",str(task.id),
                   {"store":store,"week":week.isoformat(),"frequency":frequency})
        self.commit()
        return {"id":str(task.id),"store":store,"title":title,"week_start":week.isoformat()}

    def revise_task(self,store:str,task_id:UUID,reference:date,
                    title:str,details:str,frequency:str,day:int)->dict:
        self.require(store,"checklist.edit")
        week=monday(reference)
        old=self.db.scalar(select(WeeklyTask).where(
            WeeklyTask.id==task_id,WeeklyTask.store_code==store
        ).with_for_update())
        if not old:
            raise OperationError(404,"Rotina não encontrada")
        if week<old.start_week.date():
            raise OperationError(422,"Selecione uma semana igual ou posterior ao início")
        if old.end_week is not None and week>old.end_week.date():
            raise OperationError(409,"Esta versão já está encerrada")
        if len(title.strip())<3:
            raise OperationError(422,"Título inválido")
        if frequency not in {"weekly","once"} or day<0 or day>6:
            raise OperationError(422,"Frequência ou dia inválido")
        # Keep older weekly checks intact. New version begins from selected week.
        old.end_week=start_of(week-timedelta(days=7))
        new=WeeklyTask(id=uuid4(),store_code=store,title=title.strip(),details=details,
                       frequency=frequency,scheduled_day=day,start_week=start_of(week),
                       end_week=None,active=True,created_by=self.actor.id)
        self.db.add(new)
        self.audit("checklist.task.revised","weekly_task",str(new.id),
                   {"store":store,"previous_task_id":str(old.id),"from_week":week.isoformat()})
        self.commit()
        return {"id":str(new.id),"replaces":str(old.id),"week_start":week.isoformat()}

    def verify_task(self,store:str,task_id:UUID,reference:date,done:bool)->dict:
        self.require(store,"checklist.edit")
        week=monday(reference)
        if not can_verify(week):
            raise OperationError(422,"Não é permitido validar semanas futuras")
        begin=start_of(week)
        task=self.db.scalar(select(WeeklyTask.id).where(
            WeeklyTask.id==task_id,WeeklyTask.store_code==store,
            WeeklyTask.start_week<=begin,
            or_(WeeklyTask.end_week.is_(None),WeeklyTask.end_week>=begin),
            or_(WeeklyTask.frequency=="weekly",WeeklyTask.start_week==begin),
        ))
        if not task:
            raise OperationError(404,"Rotina não programada para esta semana")
        mark=self.db.get(WeeklyTaskCheck,{"task_id":task_id,"week_start":begin})
        if mark is None:
            mark=WeeklyTaskCheck(task_id=task_id,week_start=begin,done=done,
                                 checked_by=self.actor.id)
            self.db.add(mark)
        else:
            mark.done=done;mark.checked_by=self.actor.id
            mark.checked_at=datetime.now(SAO_PAULO)
        self.audit("checklist.task.verified","weekly_task",str(task_id),
                   {"store":store,"week":week.isoformat(),"done":done})
        self.commit()
        return {"task_id":str(task_id),"week_start":week.isoformat(),"done":done}

    def weekly_goal(self,store:str,reference:date,goal:int,confirmed:bool)->dict:
        self.require(store,"checklist.edit")
        week=monday(reference)
        if confirmed and not can_verify(week):
            raise OperationError(422,"Não é permitido validar semanas futuras")
        start=start_of(week)
        entry=self.db.get(WeeklyCallGoal,{"store_code":store,"week_start":start})
        if entry is None:
            entry=WeeklyCallGoal(store_code=store,week_start=start,goal=goal,
                                 confirmed=confirmed,
                                 confirmed_by=self.actor.id if confirmed else None,
                                 updated_by=self.actor.id)
            self.db.add(entry)
        else:
            entry.goal=goal;entry.confirmed=confirmed
            entry.confirmed_by=self.actor.id if confirmed else None
            entry.updated_by=self.actor.id
        self.audit("checklist.calls.validated","weekly_call_goal",f"{store}|{week.isoformat()}",
                   {"goal":goal,"confirmed":confirmed})
        self.commit()
        return {"store_code":store,"week_start":week.isoformat(),
                "goal":goal,"confirmed":confirmed}

    def marketing(self,year:int,month:int)->dict:
        self.period(year,month)
        if not self.allowed("whatsapp_status.view"):
            raise OperationError(403,"Acesso negado")
        posts=self.db.scalars(select(WhatsAppPost).where(
            WhatsAppPost.year==year,func.extract("month",WhatsAppPost.post_date)==month
        ).order_by(WhatsAppPost.post_date)).all()
        days_off=self.db.scalars(select(WhatsAppDayOff).where(
            func.extract("year",WhatsAppDayOff.post_date)==year,
            func.extract("month",WhatsAppDayOff.post_date)==month,
        ).order_by(WhatsAppDayOff.post_date)).all()
        return {"year":year,"month":month,"scope":"global_uma",
                "posts":[self._post(row) for row in posts],
                "days_off":[{"date":day_iso(row.post_date),"reason":row.reason} for row in days_off],
                "attachments_enabled":False}

    @staticmethod
    def _post(row:WhatsAppPost)->dict:
        return {"date":day_iso(row.post_date),"product_code":row.product_code,
                "category":row.category,"note":row.note,"status":row.status,
                "published_on":row.published_on.isoformat() if row.published_on else None,
                "revision":row.revision,"has_art_file":False,
                "has_evidence_file":False}

    def delete_marketing(self, when: date, expected: int) -> dict:
        self.require("JOINVILLE", "whatsapp_status.edit")
        row = self.db.scalar(
            select(WhatsAppPost).where(
                WhatsAppPost.post_date == start_of(when)
            ).with_for_update()
        )
        if row is None:
            raise OperationError(404, "Planejamento não encontrado")
        self.revision(row, expected)
        previous = self._post(row)
        self.db.delete(row)
        self.audit("whatsapp.plan.deleted", "whatsapp_post", when.isoformat(),
                   {"previous": previous, "year": when.year})
        self.commit()
        return {"date": when.isoformat(), "deleted": True}


    def save_marketing(self,when:date,code:str,category:str,note:str,
                       status:str,expected:int)->dict:
        self.require("JOINVILLE","whatsapp_status.edit")
        if when.weekday()>=5:
            raise OperationError(422,"O calendário está programado de segunda a sexta")
        if self.db.get(WhatsAppDayOff,start_of(when)):
            raise OperationError(422,"Dia marcado sem postagem")
        key=normalize(code.strip())
        if not key:
            raise OperationError(422,"Informe o código do produto")
        old=self.db.get(WhatsAppPost,start_of(when))
        self.revision(old,expected)
        conflicting=self.db.scalar(select(WhatsAppPost).where(
            WhatsAppPost.year==when.year,WhatsAppPost.product_code_key==key,
            WhatsAppPost.post_date!=start_of(when),
        ))
        if conflicting:
            raise OperationError(409,"Código de produto já usado em outra data deste ano")
        if status not in {"planejado","arte_pronta","publicado"}:
            raise OperationError(422,"Status desconhecido")
        if old is None:
            row=WhatsAppPost(
                post_date=start_of(when),year=when.year,product_code=code.strip(),
                product_code_key=key,category=category,note=note,status=status,
                revision=1,updated_by=self.actor.id,
                published_on=datetime.now(SAO_PAULO) if status=="publicado" else None,
            )
            self.db.add(row)
        else:
            row=old
            row.product_code=code.strip();row.product_code_key=key
            row.category=category;row.note=note;row.status=status
            row.updated_by=self.actor.id;row.revision+=1
            row.published_on=(
                old.published_on or datetime.now(SAO_PAULO)
                if status=="publicado" else None
            )
        self.audit("whatsapp.plan.updated","whatsapp_post",when.isoformat(),
                   {"year":when.year,"product_code":code.strip(),"status":status,
                    "before_revision":expected})
        self.commit()
        return self._post(row)

    def set_day_off(self,when:date,off:bool,reason:str)->dict:
        self.require("JOINVILLE","whatsapp_status.edit")
        if when.weekday()>=5:
            raise OperationError(422,"Sábados e domingos não possuem postagens programadas")
        key=start_of(when)
        existing=self.db.get(WhatsAppDayOff,key)
        if off and self.db.get(WhatsAppPost,key):
            raise OperationError(409,"Remova o planejamento da data antes de marcá-la sem postagem")
        if off and not existing:
            self.db.add(WhatsAppDayOff(post_date=key,reason=reason,
                                       created_by=self.actor.id))
        if off and existing:
            existing.reason=reason
        if not off and existing:
            self.db.delete(existing)
        self.audit("whatsapp.day_off.updated","whatsapp_day",when.isoformat(),
                   {"off":off,"reason":reason})
        self.commit()
        return {"date":when.isoformat(),"off":off}

    def instagram(self,year:int,month:int)->dict:
        self.period(year,month)
        stores=self.allowed("instagram.view")
        if not stores:
            raise OperationError(403,"Acesso negado")
        entries=self.db.scalars(select(InstagramMonth).where(
            InstagramMonth.store_code.in_(stores),
            InstagramMonth.year==year,InstagramMonth.month==month
        )).all()
        found={e.store_code:e for e in entries}
        return {"year":year,"month":month,"stores":[{
            "store_code":store,
            "planned":found[store].planned if store in found else None,
            "completed":found[store].completed if store in found else None,
            "revision":found[store].revision if store in found else 0
        } for store in stores]}

    def save_instagram(self,store:str,year:int,month:int,planned:int,
                       completed:int,expected:int)->dict:
        self.require(store,"instagram.edit")
        self.period(year,month)
        row=self.db.scalar(select(InstagramMonth).where(
            InstagramMonth.store_code==store,InstagramMonth.year==year,
            InstagramMonth.month==month
        ).with_for_update())
        self.revision(row,expected)
        if row is None:
            row=InstagramMonth(id=uuid4(),store_code=store,year=year,month=month,
                               planned=planned,completed=completed,revision=1,
                               updated_by=self.actor.id)
            self.db.add(row)
        else:
            row.planned=planned;row.completed=completed;row.revision+=1
            row.updated_by=self.actor.id
        self.audit("instagram.month.updated","instagram_month",f"{store}|{year:04d}-{month:02d}",
                   {"planned":planned,"completed":completed})
        self.commit()
        return {"store_code":store,"year":year,"month":month,
                "planned":planned,"completed":completed,"revision":row.revision}

    def training(self,store:str,limit:int=100)->list[dict]:
        self.require(store,"training.view")
        rows=self.db.execute(
            select(TrainingRecord,User.display_name)
            .join(User,User.id==TrainingRecord.participant_id)
            .where(TrainingRecord.store_code==store)
            .order_by(TrainingRecord.happened_on.desc(),TrainingRecord.created_at.desc())
            .limit(limit)
        ).all()
        return [self._training(row,name) for row,name in rows]

    @staticmethod
    def _training(row:TrainingRecord,name:str)->dict:
        return {
            "id":str(row.id),"store_code":row.store_code,
            "participant_id":str(row.participant_id),"participant":name,
            "procedure":row.procedure,"version":row.version,"title":row.title,
            "instructor":row.instructor,"happened_on":row.happened_on.isoformat(),
            "step":row.step,"note":row.note,
            "signed":False,"document_attached":False,
        }

    def add_training(self,store:str,participant_id:UUID,procedure:str,version:str,
                     title:str,instructor:str,happened_on:datetime,
                     step:str,note:str)->dict:
        self.require(store,"training.edit")
        if not self._seller_in_store(store,participant_id):
            raise OperationError(422,"Colaborador não cadastrado na loja selecionada")
        entry=TrainingRecord(
            id=uuid4(),store_code=store,participant_id=participant_id,
            procedure=procedure.strip(),version=version.strip(),
            title=title,instructor=instructor.strip(),happened_on=happened_on,
            step=step,note=note,recorded_by=self.actor.id,
        )
        self.db.add(entry)
        self.audit("training.registered","training_record",str(entry.id),
                   {"store":store,"participant_id":str(participant_id),
                    "procedure":procedure,"version":version,"step":step,
                    "signed":False})
        self.commit()
        person=self.db.get(User,participant_id)
        return self._training(entry,person.display_name)
