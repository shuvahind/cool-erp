"""Сервис управления пользователями с контролем доступа и аудитом."""
import logging
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import service as audit_service
from app.core.users.crud import crud_user
from app.core.users.models import UserModel
from app.core.users.registration_service import registration_service
from app.core.users.schemas import (
    PublicRegisterSchema,
    UserRegisterSchema,
    UserUpdateSchema,
)

logger = logging.getLogger(__name__)


class UserService:
    """Бизнес-логика управления пользователями."""

    async def create_by_admin(
        self,
        db: AsyncSession,
        *,
        user_in: UserRegisterSchema,
        current_session: Any,  # UserProtocol
    ) -> UserModel:
        """Создание пользователя администратором или суперадмином."""
        if not current_session.is_admin and not current_session.is_superadmin:
            raise PermissionError("Создание пользователей доступно только администратору или суперадмину")

        if not current_session.is_superadmin and user_in.tenant_id != current_session.tenant_id:
            raise PermissionError("Нет доступа к другой организации")

        existing_user = await crud_user.get_by_email(db, email=user_in.email)
        if existing_user:
            raise ValueError("Пользователь с таким email уже существует")

        # 1. Создаём
        new_user = await crud_user.register_new_user(db, user_in=user_in)
   

        # 2. Аудит создания
        await audit_service.log_data_create(
            db,
            tenant_id=new_user.tenant_id,
            user_id=current_session.id,
            entity_type="user",
            entity_id=new_user.id,
            entity_name=new_user.email,
            changes={
                "name": new_user.name,
                "email": new_user.email,
                "tenant_id": str(new_user.tenant_id),
                "is_admin": new_user.is_admin,
                "is_superadmin": new_user.is_superadmin,
            },
        )

        await db.commit()
        # ✅ Загружаем пользователя заново (вместо refresh)
        new_user = await crud_user.get(db, id=new_user.id)
        if new_user is None:
            raise ValueError("Пользователь не найден после создания")
        return new_user

    async def update(
        self,
        db: AsyncSession,
        *,
        user_id: uuid.UUID,
        user_changes: UserUpdateSchema,
        current_session: Any,  # UserProtocol
    ) -> UserModel:
        """Обновление пользователя с проверкой прав и фиксацией пароля в аудите."""
        db_user = await crud_user.get(db, id=user_id)
        if db_user is None:
            raise ValueError("Пользователь не найден")

        # 1. Проверки прав доступа
        if not current_session.is_superadmin:
            if db_user.id != current_session.id:
                if not current_session.is_admin:
                    raise PermissionError("Нет доступа к профилю другого пользователя")
                if db_user.tenant_id != current_session.tenant_id:
                    raise PermissionError("Нет доступа к пользователю другой организации")

        if user_changes.is_superadmin is not None and user_changes.is_superadmin and not current_session.is_superadmin:
            raise PermissionError("Назначение суперадминистратора доступно только суперадмину")

        if user_changes.tenant_id is not None and user_changes.tenant_id != db_user.tenant_id and not current_session.is_superadmin:
            raise PermissionError("Смена организации доступна только суперадмину")

        if user_changes.is_admin is not None and not current_session.is_admin and not current_session.is_superadmin:
            raise PermissionError("Назначение администратора доступно только администратору или суперадмину")

        if user_changes.role_ids is not None and not current_session.is_admin and not current_session.is_superadmin:
            raise PermissionError("Назначение ролей доступно только администратору или суперадмину")

        # 2. Собираем old_values ДО update
        old_values: dict[str, uuid.UUID | str | bool | None] = {}
        for field in UserUpdateSchema.model_fields:
            if field in user_changes.model_dump(exclude_unset=True):
                old_values[field] = getattr(db_user, field, None)

        # 3. Обновляем через CRUD
        updated_user, trigger_logout = await crud_user.update_user(
            db, db_user=db_user, user_changes=user_changes
        )

        # 4. Готовим данные для аудита (скрываем пароль)
        new_values_for_audit = user_changes.model_dump(exclude_unset=True)
        old_values_for_audit = dict(old_values)

        if "password" in new_values_for_audit:
            new_values_for_audit["password"] = "*** (изменён)"
            if "password" in old_values_for_audit:
                old_values_for_audit["password"] = "********"

        # 5. Аудит обновления
        await audit_service.log_data_update(
            db,
            tenant_id=updated_user.tenant_id,
            user_id=current_session.id,
            entity_type="user",
            entity_id=updated_user.id,
            entity_name=updated_user.email,
            old_values=old_values_for_audit,
            new_values=new_values_for_audit,
        )

        await db.commit()
        await db.refresh(updated_user)

        if trigger_logout:
            crud_user.clear_user_sessions(updated_user.id)

        return updated_user

    async def delete(
        self,
        db: AsyncSession,
        *,
        user_id: uuid.UUID,
        current_session: Any,  # UserProtocol
    ) -> UserModel:
        """Удаление пользователя с автоматическим аудитом."""
        if not current_session.is_admin and not current_session.is_superadmin:
            raise PermissionError("Удаление пользователей доступно только администратору или суперадмину")

        if user_id == current_session.id:
            raise ValueError("Нельзя удалить собственный аккаунт")

        deleted_user = await crud_user.get(db, id=user_id)
        if deleted_user is None:
            raise ValueError("Пользователь не найден")

        if not current_session.is_superadmin and deleted_user.tenant_id != current_session.tenant_id:
            raise PermissionError("Нет доступа к пользователю другой организации")

        # 1. Удаляем (мягко)
        result = await crud_user.remove(db, id=user_id)
        if result is None:
            raise ValueError("Пользователь не найден")

        # 2. Аудит — автоматический сбор снимка
        await audit_service.log_data_delete_snapshot(
            db,
            tenant_id=deleted_user.tenant_id,
            user_id=current_session.id,
            entity_type="user",
            entity_id=deleted_user.id,
            entity_name=deleted_user.name,
            obj=deleted_user,
        )

        await db.commit()

        # 3. Очистка сессий после commit
        crud_user.clear_user_sessions(deleted_user.id)

        return deleted_user

    async def public_register(
        self,
        db: AsyncSession,
        *,
        user_in: PublicRegisterSchema,
    ) -> tuple[UserModel, bool]:
        """Публичная регистрация (создаёт пользователя + возможно тенанта)."""
        existing_user = await crud_user.get_by_email(db, email=user_in.email)
        if existing_user:
            raise ValueError("Пользователь с таким email уже существует")

        new_user, is_new_tenant = await registration_service.register(db, user_in=user_in)

        await audit_service.log_data_create(
            db,
            tenant_id=new_user.tenant_id,
            user_id=new_user.id,
            entity_type="user",
            entity_id=new_user.id,
            entity_name=new_user.email,
            changes={
                "name": new_user.name,
                "email": new_user.email,
                "tenant_id": str(new_user.tenant_id),
                "is_new_tenant": is_new_tenant,
            },
        )

        await db.commit()
        new_user = await crud_user.get(db, id=new_user.id)
        if new_user is None:
            raise ValueError("Пользователь не найден после создания")
        return new_user, is_new_tenant


user_service = UserService()