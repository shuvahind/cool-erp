"""backend/app/core/roles/router.py"""

import logging
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select

from app.core.audit import service as audit_service
from app.core.auth.dependencies import CurrentUser, DBSession
from app.core.roles.crud import crud_role
from app.core.roles.schemas import (
    RoleCreateSchema,
    RoleUpdateSchema,
    RoleResponseSchema,
    RoleSaveSchema,
)
from app.core.roles.services import role_service
from app.core.schemas import ApiResponse, PaginatedResponse
from app.core.permissions.models import PermissionModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/roles", tags=["Roles"])


# ==================================================================
# СПИСОК РОЛЕЙ
# ==================================================================
@router.get("/", response_model=ApiResponse[PaginatedResponse[RoleResponseSchema]])
async def get_roles(
    db: DBSession,
    session: CurrentUser,
    skip: int = Query(0, ge=0),
    limit: int = Query(10, gt=0, le=1000),
    search: str | None = None,
) -> ApiResponse[PaginatedResponse[RoleResponseSchema]]:
    """Получение списка ролей с пагинацией и поиском."""
    is_superadmin = bool(session.is_superadmin)

    items, total = await crud_role.get_multi(
        db,
        skip=skip,
        limit=limit,
        search=search,
        current_tenant_id=session.tenant_id,
        is_superadmin=is_superadmin,
    )

    paginated_data = PaginatedResponse(
        items=[RoleResponseSchema.model_validate(item) for item in items],
        total=total,
        page=(skip // limit) + 1,
        size=limit,
    )
    return ApiResponse(
        success=True,
        message="Роли успешно получены",
        data=paginated_data,
    )


# ==================================================================
# ОДНА РОЛЬ
# ==================================================================
@router.get("/{role_id}", response_model=ApiResponse[RoleResponseSchema])
async def get_role(
    role_id: uuid.UUID,
    db: DBSession,
    session: CurrentUser,
) -> ApiResponse[RoleResponseSchema]:
    """Получение одной роли по ID."""
    is_superadmin = bool(session.is_superadmin)

    role = await crud_role.get(
        db,
        item_id=role_id,
        current_tenant_id=session.tenant_id,
        is_superadmin=is_superadmin,
    )
    if not role:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Роль не найдена"
        )

    return ApiResponse(
        success=True,
        message="Роль успешно получена",
        data=RoleResponseSchema.model_validate(role),
    )


# ==================================================================
# СОЗДАНИЕ РОЛИ (аудит в роутере — как goods)
# ==================================================================
@router.post("/", response_model=ApiResponse[RoleResponseSchema], status_code=201)
async def create_role(
    data: RoleCreateSchema,
    db: DBSession,
    session: CurrentUser,
) -> ApiResponse[RoleResponseSchema]:
    """Создание новой роли."""
    is_superadmin = bool(session.is_superadmin)

    try:
        role = await crud_role.create(
            db,
            data=data,
            current_tenant_id=session.tenant_id,
            is_superadmin=is_superadmin,
        )

        # ✅ Аудит создания — в роутере (как goods)
        await audit_service.log_data_create(
            db,
            tenant_id=role.tenant_id,
            user_id=session.id,
            entity_type="role",
            entity_id=role.id,
            entity_name=role.name,
            changes=data.model_dump(mode="json"),
        )

        await db.commit()
        await db.refresh(role)
    except HTTPException:
        await db.rollback()
        raise
    except Exception as exc:
        await db.rollback()
        logger.error("Ошибка создания роли: %s", str(exc), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ошибка создания роли",
        ) from exc

    return ApiResponse(
        success=True,
        message="Роль успешно создана",
        data=RoleResponseSchema.model_validate(role),
    )


# ==================================================================
# ОБНОВЛЕНИЕ РОЛИ (аудит в роутере — как goods)
# ==================================================================
@router.put("/{role_id}", response_model=ApiResponse[RoleResponseSchema])
async def update_role(
    role_id: uuid.UUID,
    data: RoleUpdateSchema,
    db: DBSession,
    session: CurrentUser,
) -> ApiResponse[RoleResponseSchema]:
    """Обновление существующей роли."""
    is_superadmin = bool(session.is_superadmin)

    # ✅ old_values собираем ДО update — как в goods update
    role_before = await crud_role.get(
        db,
        item_id=role_id,
        current_tenant_id=session.tenant_id,
        is_superadmin=is_superadmin,
    )
    if role_before is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Роль не найдена"
        )

    old_values: dict[str, Any] = {}
    dump = data.model_dump(exclude_unset=True)
    for field in RoleUpdateSchema.model_fields:
        if field in dump:
            old_values[field] = getattr(role_before, field, None)

    old_values["user_ids"] = (
        [u.id for u in role_before.users] if role_before.users else []
    )
    old_values["section_ids"] = role_before.section_ids or []

    old_perms_stmt = select(PermissionModel).where(PermissionModel.role_id == role_id)
    old_perms_result = await db.execute(old_perms_stmt)
    old_perms = list(old_perms_result.scalars().all())

    new_perms = dump.get("permissions", [])
    
    # ✅ Вызываем метод из сервиса
    old_perm_str, new_perm_str = role_service.format_permissions_for_audit(
        old_perms, new_perms
    )

    if old_perm_str:
        old_values["permissions"] = old_perm_str
        dump["permissions"] = new_perm_str
    else:
        old_values.pop("permissions", None)
        dump.pop("permissions", None)

    try:
        role = await crud_role.update(
            db,
            item_id=role_id,
            data=data,
            current_tenant_id=session.tenant_id,
            is_superadmin=is_superadmin,
        )

        # ✅ Аудит обновления — в роутере (как goods)
        await audit_service.log_data_update(
            db,
            tenant_id=role.tenant_id,
            user_id=session.id,
            entity_type="role",
            entity_id=role.id,
            entity_name=role.name,
            old_values=old_values,
            new_values=dump,
        )

        await db.commit()
        await db.refresh(role)
    except HTTPException:
        await db.rollback()
        raise
    except Exception as exc:
        await db.rollback()
        logger.error("Ошибка обновления роли %s: %s", role_id, str(exc), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ошибка обновления роли",
        ) from exc

    return ApiResponse(
        success=True,
        message="Роль успешно обновлена",
        data=RoleResponseSchema.model_validate(role),
    )


# ==================================================================
# УДАЛЕНИЕ РОЛИ (аудит В СЕРВИСЕ)
# ==================================================================
@router.delete("/{role_id}", response_model=ApiResponse[RoleResponseSchema])
async def delete_role(
    role_id: uuid.UUID,
    db: DBSession,
    session: CurrentUser,
) -> ApiResponse[RoleResponseSchema]:
    """Удаление роли (каскадно удалит все её permissions)."""
    try:
        # ✅ Всё делает сервис: загружает, удаляет, пишет аудит
        deleted_role = await role_service.delete(
            db,
            role_id=role_id,
            current_session=session,
        )
        await db.commit()
    except ValueError as exc:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except Exception as exc:
        await db.rollback()
        logger.error("Ошибка удаления роли %s: %s", role_id, str(exc), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ошибка удаления роли",
        ) from exc

    return ApiResponse(
        success=True,
        message="Роль удалена",
        data=RoleResponseSchema.model_validate(deleted_role),
    )


# ==================================================================
# АГРЕГИРОВАННОЕ СОХРАНЕНИЕ РОЛИ (аудит в роутере — как goods)
# ==================================================================
@router.post("/save", response_model=ApiResponse[RoleResponseSchema], status_code=201)
async def save_role(
    data: RoleSaveSchema,
    db: DBSession,
    session: CurrentUser,
    role_id: uuid.UUID | None = None,
) -> ApiResponse[RoleResponseSchema]:
    """
    Агрегированное сохранение роли:
    создание/обновление + синхронизация полномочий и пользователей.
    """
    is_superadmin = bool(session.is_superadmin)

    old_values: dict[str, Any] = {}
    dump = data.model_dump(exclude_unset=True)

    if role_id:
        role_before = await crud_role.get(
            db,
            item_id=role_id,
            current_tenant_id=session.tenant_id,
            is_superadmin=is_superadmin,
        )
        if role_before is not None:
            for field in RoleSaveSchema.model_fields:
                if field in dump:
                    old_values[field] = getattr(role_before, field, None)

            old_values["user_ids"] = (
                [u.id for u in role_before.users] if role_before.users else []
            )
            old_values["section_ids"] = role_before.section_ids or []

            old_perms_stmt = select(PermissionModel).where(
                PermissionModel.role_id == role_id
            )
            old_perms_result = await db.execute(old_perms_stmt)
            old_perms = list(old_perms_result.scalars().all())

            new_perms = dump.get("permissions", [])
            
            # ✅ Вызываем метод из сервиса
            old_perm_str, new_perm_str = role_service.format_permissions_for_audit(
                old_perms, new_perms
            )

            if old_perm_str:
                old_values["permissions"] = old_perm_str
                dump["permissions"] = new_perm_str
            else:
                old_values.pop("permissions", None)
                dump.pop("permissions", None)

    try:
        role = await role_service.save_role(
            db,
            data=data,
            current_tenant_id=session.tenant_id,
            is_superadmin=is_superadmin,
            role_id=role_id,
        )

        # ✅ Аудит — в роутере (как goods)
        if role_id:
            await audit_service.log_data_update(
                db,
                tenant_id=role.tenant_id,
                user_id=session.id,
                entity_type="role",
                entity_id=role.id,
                entity_name=role.name,
                old_values=old_values,
                new_values=dump,
            )
        else:
            await audit_service.log_data_create(
                db,
                tenant_id=role.tenant_id,
                user_id=session.id,
                entity_type="role",
                entity_id=role.id,
                entity_name=role.name,
                changes=dump,
            )

        await db.commit()
        await db.refresh(role)
    except HTTPException:
        await db.rollback()
        raise
    except Exception as exc:
        await db.rollback()
        logger.error("Ошибка сохранения роли: %s", str(exc), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ошибка сохранения роли",
        ) from exc

    return ApiResponse(
        success=True,
        message="Роль и её полномочия успешно сохранены",
        data=RoleResponseSchema.model_validate(role),
    )