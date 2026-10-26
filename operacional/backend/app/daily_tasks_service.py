"""Tarefas pontuais por dia e por loja; independentes do ERP.

Somente administradores criam, editam ou concluem nesta primeira fase.
Vendedores podem consultar apenas a própria unidade, com permissão explícita.
"""
from datetime import date, datetime
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import select
from app.models import DailyTask, User
from app.operations_service import OperationsService, OperationError, date_time, day_iso


SAO_PAULO = ZoneInfo("America/Sao_Paulo")
STATUS = {"pendente", "em_andamento", "concluida"}
PRIORITIES = {"baixa", "normal", "alta"}


class DailyTaskService(OperationsService):
    @staticmethod
    def valid_date(day: date) -> None:
        if not 2020 <= day.year <= 2100:
            raise OperationError(422, "Selecione uma data entre 2020 e 2100")

    def valid_assignee(self, store: str, assignee_id: UUID | None) -> None:
        if assignee_id is not None and not self._seller_in_store(store, assignee_id):
            raise OperationError(422, "Responsável não cadastrado ou inativo nesta loja")

    def _seller_in_store(self, store: str, seller_id: UUID) -> bool:
        # Reaproveita a consulta de identidade do módulo de ligações.
        from app.operations_service import OperationsService
        return OperationsService._seller_in_store(self, store, seller_id)

    @staticmethod
    def item(row: DailyTask, assignee: str | None) -> dict:
        return {
            "id": str(row.id), "store_code": row.store_code,
            "date": day_iso(row.due_on), "title": row.title,
            "details": row.details, "priority": row.priority,
            "status": row.status,
            "assignee_id": str(row.assignee_id) if row.assignee_id else None,
            "assignee": assignee or ("Responsável indisponível" if row.assignee_id else "Equipe da loja"),
            "completed_at": row.completed_at.isoformat() if row.completed_at else None,
            "revision": row.revision,
        }

    def _item(self, row: DailyTask) -> dict:
        person = self.db.get(User, row.assignee_id) if row.assignee_id else None
        return self.item(row, person.display_name if person else None)

    def list(self, store: str, day: date) -> dict:
        self.require(store, "daily_tasks.view")
        self.valid_date(day)
        rows = self.db.execute(
            select(DailyTask, User.display_name)
            .outerjoin(User, User.id == DailyTask.assignee_id)
            .where(DailyTask.store_code == store,
                   DailyTask.due_on == date_time(day),
                   DailyTask.deleted_at.is_(None))
            .order_by(DailyTask.id)
        ).all()
        items = [self.item(task, name) for task, name in rows]
        return {
            "store_code": store, "date": day.isoformat(), "items": items,
            "summary": {
                "total": len(items),
                "pending": sum(t["status"] == "pendente" for t in items),
                "in_progress": sum(t["status"] == "em_andamento" for t in items),
                "completed": sum(t["status"] == "concluida" for t in items),
            },
        }

    def create(self, store: str, day: date, title: str, details: str,
               priority: str, assignee_id: UUID | None) -> dict:
        self.require(store, "daily_tasks.edit")
        self.valid_date(day)
        self.valid_assignee(store, assignee_id)
        title = title.strip()
        if len(title) < 3 or priority not in PRIORITIES:
            raise OperationError(422, "Título ou prioridade inválidos")
        task = DailyTask(
            id=uuid4(), store_code=store, due_on=date_time(day), title=title,
            details=details.strip(), priority=priority, status="pendente",
            revision=1, assignee_id=assignee_id,
            created_by=self.actor.id, updated_by=self.actor.id,
        )
        self.db.add(task)
        self.audit("daily_task.created", "daily_task", str(task.id),
                   {"store": store, "date": day.isoformat(),
                    "priority": priority, "assignee_id": str(assignee_id) if assignee_id else None})
        self.commit()
        return self._item(task)

    def update(self, store: str, task_id: UUID, *, day: date,
               title: str, details: str, priority: str,
               status: str, assignee_id: UUID | None,
               expected_revision: int) -> dict:
        self.require(store, "daily_tasks.edit")
        self.valid_date(day)
        self.valid_assignee(store, assignee_id)
        title = title.strip()
        if len(title) < 3 or priority not in PRIORITIES or status not in STATUS:
            raise OperationError(422, "Informações da tarefa inválidas")
        task = self.db.scalar(
            select(DailyTask).where(
                DailyTask.store_code == store, DailyTask.id == task_id,
                DailyTask.deleted_at.is_(None)
            ).with_for_update()
        )
        if task is None:
            raise OperationError(404, "Tarefa não encontrada nesta loja")
        self.revision(task, expected_revision)
        before = {
            "date": day_iso(task.due_on), "status": task.status,
            "priority": task.priority,
            "assignee_id": str(task.assignee_id) if task.assignee_id else None,
        }
        task.due_on = date_time(day)
        task.title = title
        task.details = details.strip()
        task.priority = priority
        task.assignee_id = assignee_id
        if status == "concluida" and task.status != "concluida":
            task.completed_at = datetime.now(SAO_PAULO)
        elif status != "concluida":
            task.completed_at = None
        task.status = status
        task.revision += 1
        task.updated_by = self.actor.id
        task.updated_at = datetime.now(SAO_PAULO)
        self.audit("daily_task.updated", "daily_task", str(task.id),
                   {"store": store, "before": before,
                    "after": {"date": day.isoformat(), "status": status,
                              "priority": priority,
                              "assignee_id": str(assignee_id) if assignee_id else None},
                    "revision": task.revision})
        self.commit()
        return self._item(task)

    def remove(self, store: str, task_id: UUID, expected_revision: int) -> dict:
        self.require(store, "daily_tasks.edit")
        task = self.db.scalar(
            select(DailyTask).where(
                DailyTask.store_code == store, DailyTask.id == task_id,
                DailyTask.deleted_at.is_(None)
            ).with_for_update()
        )
        if task is None:
            raise OperationError(404, "Tarefa não encontrada nesta loja")
        self.revision(task, expected_revision)
        task.deleted_at = datetime.now(SAO_PAULO)
        task.updated_by = self.actor.id
        task.updated_at = datetime.now(SAO_PAULO)
        task.revision += 1
        self.audit("daily_task.deleted", "daily_task", str(task.id),
                   {"store": store, "date": day_iso(task.due_on),
                    "revision": expected_revision, "soft_delete": True})
        self.commit()
        return {"id": str(task.id), "deleted": True}
