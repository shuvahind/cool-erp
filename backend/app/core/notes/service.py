"""backend/app/core/notes/service.py"""
import logging
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.access.schemas import UserProtocol
from app.core.audit import service as audit_service
from app.core.notes.crud import crud_note
from app.core.notes.exceptions import NoteNotFoundError
from app.core.notes.models import NotesModel
from app.core.notes.schemas import (
    NoteCreateSchema,
    NoteUpdateSchema,
)

logger = logging.getLogger(__name__)


class NoteService:
    """Сервис для управления заметками с аудитом и блокировками."""

    async def create(
        self,
        db: AsyncSession,
        *,
        obj_in: NoteCreateSchema,
        user: UserProtocol,
        user_id: uuid.UUID,
        current_tenant_id: uuid.UUID,
        is_superadmin: bool = False,
    ) -> NotesModel:
        """Создание заметки + аудит."""
        note = await crud_note.create_for_user(
            db,
            obj_in=obj_in,
            user=user,
            tenant_id=current_tenant_id,
            is_superadmin=is_superadmin,
        )

        # ✅ Аудит создания
        await audit_service.log_data_create(
            db,
            tenant_id=note.tenant_id,
            user_id=user_id,
            entity_type="note",
            entity_id=note.id,
            entity_name=note.title,
            changes=obj_in.model_dump(mode="json"),
        )

        return note

    async def update(
        self,
        db: AsyncSession,
        *,
        note_id: uuid.UUID,
        obj_in: NoteUpdateSchema,
        user: UserProtocol,
        user_id: uuid.UUID,
        current_tenant_id: uuid.UUID,
        is_superadmin: bool = False,
    ) -> NotesModel:
        """Обновление заметки + аудит (сбор old_values внутри)."""
        # ✅ Собираем old_values ДО обновления
        note_before = await crud_note.get(db, id=note_id)
        old_values: dict[str, Any] = {}
        
        if note_before is not None:
            dump = obj_in.model_dump(exclude_unset=True)
            for field in NoteUpdateSchema.model_fields:
                if field in dump:
                    old_values[field] = getattr(note_before, field, None)

        # ✅ Сохраняем с проверкой версии и блокировки
        note = await crud_note.save_with_version(
            db,
            note_id=note_id,
            obj_in=obj_in,
            user=user,
            tenant_id=current_tenant_id,
            user_id=user_id,
            is_superadmin=is_superadmin,
        )

        # ✅ Аудит обновления
        await audit_service.log_data_update(
            db,
            tenant_id=note.tenant_id,
            user_id=user_id,
            entity_type="note",
            entity_id=note.id,
            entity_name=note.title,
            old_values=old_values,
            new_values=obj_in.model_dump(exclude_unset=True),
        )

        return note

    async def delete(
        self,
        db: AsyncSession,
        *,
        note_id: uuid.UUID,
        user: UserProtocol,
        user_id: uuid.UUID,
        current_tenant_id: uuid.UUID,
        is_superadmin: bool = False,
    ) -> NotesModel:
        """Мягкое удаление + автосбор снимка."""
        # 1. Загружаем заметку ДО удаления (для снимка)
        note_before = await crud_note.get(db, id=note_id)
        if not note_before:
            raise NoteNotFoundError("Заметка не найдена")

        # 2. Удаляем
        note = await crud_note.mark_deleted(
            db,
            note_id=note_id,
            user=user,
            tenant_id=current_tenant_id,
            user_id=user_id,
            is_superadmin=is_superadmin,
        )

        # 3. Аудит (автосбор всех колонок модели)
        await audit_service.log_data_delete_snapshot(
            db,
            tenant_id=note.tenant_id,
            user_id=user_id,
            entity_type="note",
            entity_id=note.id,
            entity_name=note.title,
            obj=note_before,
        )

        return note

    async def acquire_lock(
        self,
        db: AsyncSession,
        *,
        note_id: uuid.UUID,
        user: UserProtocol,
        user_id: uuid.UUID,
        current_tenant_id: uuid.UUID,
        is_superadmin: bool = False,
    ) -> NotesModel:
        """Захват пессимистической блокировки."""
        note = await crud_note.acquire_editing_lock(
            db,
            note_id=note_id,
            user=user,
            tenant_id=current_tenant_id,
            user_id=user_id,
            is_superadmin=is_superadmin,
        )
        return note

    async def release_lock(
        self,
        db: AsyncSession,
        *,
        note_id: uuid.UUID,
        user: UserProtocol,
        user_id: uuid.UUID,
        current_tenant_id: uuid.UUID,
        is_superadmin: bool = False,
    ) -> NotesModel:
        """Освобождение пессимистической блокировки."""
        note = await crud_note.release_editing_lock(
            db,
            note_id=note_id,
            user=user,
            tenant_id=current_tenant_id,
            user_id=user_id,
            is_superadmin=is_superadmin,
        )
        return note


note_service = NoteService()