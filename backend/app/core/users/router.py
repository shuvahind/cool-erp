"""backend/app/core/users/router.py"""
import logging
import uuid
from typing import Any, Mapping

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import text as sql_text

from app.core.auth.dependencies import CurrentUser, DBSession
from app.core.schemas import ApiResponse, PaginatedResponse
from app.core.users.crud import crud_user
from app.core.users.schemas import (
    PublicRegisterResponseSchema,
    PublicRegisterSchema,
    TagUserResponseSchema,
    TagWithUsersResponseSchema,
    UserRegisterSchema,
    UserResponseSchema,
    UserUpdateSchema,
)
from app.core.users.service import user_service  # <--- НАШ СЕРВИС

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/users", tags=["Users"])


# ==================================================================
# ПУБЛИЧНАЯ РЕГИСТРАЦИЯ
# ==================================================================
@router.post(
    "/public/register",
    status_code=status.HTTP_201_CREATED,
    response_model=PublicRegisterResponseSchema,
)
async def public_register(
    user_in: PublicRegisterSchema,
    db: DBSession,
) -> PublicRegisterResponseSchema:
    """Публичная регистрация гостя (создаёт нового пользователя + возможно нового тенанта)."""
    try:
        new_user, is_new_tenant = await user_service.public_register(db, user_in=user_in)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        )
    except Exception as e:
        logger.error("Ошибка при регистрации: %s", str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ошибка при регистрации: {str(e)}",
        )

    return PublicRegisterResponseSchema(
        id=new_user.id,
        name=new_user.name,
        email=new_user.email,
        tenant_id=new_user.tenant_id,
        is_admin=new_user.is_admin,
        is_superadmin=new_user.is_superadmin or False,
        is_new_tenant=is_new_tenant,
        tenant_name=user_in.tenant_name,
    )


# ==================================================================
# РЕГИСТРАЦИЯ ПОЛЬЗОВАТЕЛЯ АДМИНИСТРАТОРОМ
# ==================================================================
@router.post(
    "/register",
    status_code=status.HTTP_201_CREATED,
    response_model=ApiResponse[UserResponseSchema],
)
async def register(
    user_in: UserRegisterSchema,
    db: DBSession,
    session: CurrentUser,
) -> ApiResponse[UserResponseSchema]:
    """Регистрация нового пользователя администратором или суперадмином."""
    try:
        new_user = await user_service.create_by_admin(db, user_in=user_in, current_session=session)
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except Exception as e:
        logger.error("Ошибка создания пользователя: %s", str(e))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ошибка создания пользователя",
        )

    return ApiResponse(
        success=True,
        message="Пользователь создан",
        data=UserResponseSchema.model_validate(new_user),
    )


# ==================================================================
# СПИСОК ПОЛЬЗОВАТЕЛЕЙ
# ==================================================================
@router.get(
    "/",
    response_model=ApiResponse[PaginatedResponse[UserResponseSchema]],
)
async def read_users(
    db: DBSession,
    session: CurrentUser,
    tenant_id: uuid.UUID | None = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, gt=0, le=1000),
    search: str | None = None,
) -> ApiResponse[PaginatedResponse[UserResponseSchema]]:
    """Получение списка пользователей с пагинацией."""
    is_superadmin: bool = bool(session.is_superadmin)

    if tenant_id and not is_superadmin:
        tenant_id = session.tenant_id

    items, total = await crud_user.get_multi_paginated(
        db,
        tenant_id=session.tenant_id,
        skip=skip,
        limit=limit,
        search=search,
        user_is_superadmin=is_superadmin,
        target_tenant_id=tenant_id,
    )

    return ApiResponse(
        success=True,
        message="Пользователи получены",
        data=PaginatedResponse[UserResponseSchema](
            items=[UserResponseSchema.model_validate(item) for item in items],
            total=total,
            page=(skip // limit) + 1,
            size=limit,
        ),
    )


# ==================================================================
# ТЕГИ С ПОЛЬЗОВАТЕЛЯМИ
# ==================================================================
@router.get(
    "/tags",
    response_model=ApiResponse[list[TagWithUsersResponseSchema]],
)
async def get_tags_with_users(
    db: DBSession,
    session: CurrentUser,
) -> ApiResponse[list[TagWithUsersResponseSchema]]:
    """Список тегов доступа и пользователей."""
    is_superadmin: bool = bool(session.is_superadmin)

    where_clause: str
    params: Mapping[str, Any]

    if is_superadmin:
        where_clause = ""
        params = {}
    else:
        where_clause = "WHERE u.tenant_id = :tenant_id"
        params = {"tenant_id": session.tenant_id}

    query = sql_text(f"""
        SELECT
            distinct_tags.tag AS tag,
            json_agg(
                json_build_object(
                    'id', u.id,
                    'name', u.name,
                    'email', u.email,
                    'tenant_id', u.tenant_id,
                    'tenant_name', t.name,
                    'tags', COALESCE(u.tags, ARRAY[]::varchar[])
                ) ORDER BY u.name
            ) AS users
        FROM (
            SELECT DISTINCT unnest(u0.tags) AS tag
            FROM public.users AS u0
            WHERE u0.tags IS NOT NULL
              AND array_length(u0.tags, 1) > 0
        ) AS distinct_tags
        JOIN public.users AS u
            ON u.tags @> ARRAY[distinct_tags.tag]::varchar[]
        LEFT JOIN public.tenants AS t
            ON t.id = u.tenant_id
        {where_clause}
        GROUP BY distinct_tags.tag
        ORDER BY distinct_tags.tag
    """)

    result = await db.execute(query, params)
    rows = result.all()

    items: list[TagWithUsersResponseSchema] = []
    for row in rows:
        raw_users: list[dict[str, Any]] = list(row.users or [])
        users = [TagUserResponseSchema.model_validate(u) for u in raw_users]
        items.append(TagWithUsersResponseSchema(tag=row.tag, users=users))

    return ApiResponse(
        success=True,
        message="Теги получены",
        data=items,
    )


# ==================================================================
# ОДИН ПОЛЬЗОВАТЕЛЬ
# ==================================================================
@router.get(
    "/{user_id}",
    response_model=ApiResponse[UserResponseSchema],
)
async def read_user(
    user_id: uuid.UUID,
    db: DBSession,
    session: CurrentUser,
) -> ApiResponse[UserResponseSchema]:
    """Получение одного пользователя по UUID."""
    db_user = await crud_user.get(db, id=user_id)
    if db_user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Пользователь не найден",
        )

    if not session.is_superadmin:
        if db_user.id != session.id:
            if not session.is_admin:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Нет доступа к профилю другого пользователя",
                )
            if db_user.tenant_id != session.tenant_id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Нет доступа к пользователю другой организации",
                )

    return ApiResponse(
        success=True,
        message="Пользователь получен",
        data=UserResponseSchema.model_validate(db_user),
    )


# ==================================================================
# ОБНОВЛЕНИЕ ПОЛЬЗОВАТЕЛЯ (ТОНКИЙ РОУТЕР)
# ==================================================================
@router.put(
    "/{user_id}",
    response_model=ApiResponse[UserResponseSchema],
)
async def update_user(
    user_id: uuid.UUID,
    user_changes: UserUpdateSchema,
    db: DBSession,
    session: CurrentUser,
) -> ApiResponse[UserResponseSchema]:
    """Обновление пользователя."""
    try:
        updated_user = await user_service.update(
            db, user_id=user_id, user_changes=user_changes, current_session=session
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except Exception as e:
        logger.error("Ошибка обновления пользователя %s: %s", user_id, str(e))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ошибка обновления пользователя",
        )

    return ApiResponse(
        success=True,
        message="Пользователь обновлён",
        data=UserResponseSchema.model_validate(updated_user),
    )


# ==================================================================
# УДАЛЕНИЕ ПОЛЬЗОВАТЕЛЯ (ТОНКИЙ РОУТЕР)
# ==================================================================
@router.delete(
    "/{user_id}",
    status_code=status.HTTP_200_OK,
    response_model=ApiResponse[UserResponseSchema],
)
async def delete_user(
    user_id: uuid.UUID,
    db: DBSession,
    session: CurrentUser,
) -> ApiResponse[UserResponseSchema]:
    """Удаление пользователя из базы данных."""
    try:
        deleted_user = await user_service.delete(
            db, user_id=user_id, current_session=session
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except Exception as e:
        logger.error("Ошибка удаления пользователя %s: %s", user_id, str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Ошибка удаления пользователя",
        )

    return ApiResponse(
        success=True,
        message=f"Пользователь {deleted_user.name} успешно удалён",
        data=UserResponseSchema.model_validate(deleted_user),
    )