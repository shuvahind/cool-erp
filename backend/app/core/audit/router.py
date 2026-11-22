"""backend/app/core/audit/router.py"""

import csv
import logging
from datetime import datetime, time, timedelta
from io import StringIO
from typing import Any, AsyncIterator, cast, Tuple
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy import ColumnElement, and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit.models import AccessAuditLog, DataAuditLog
from app.core.audit.schemas import AuditAccessRead, AuditDataRead
from app.core.auth.dependencies import CurrentUser, DBSession
from app.core.schemas import ApiResponse, PaginatedResponse
from app.core.users.models import UserModel as User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/audit", tags=["Audit: access logs"])


# ==================================================================
# ПРОВЕРКА ПРАВ
# ==================================================================
def _ensure_audit_access(session: CurrentUser) -> None:
    """Аудит доступен только администратору или суперадмину."""
    if not session.is_superadmin and not session.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Просмотр аудита доступен только администратору или суперадмину",
        )


# ==================================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ==================================================================
async def _collect_user_emails(
    db: AsyncSession,
    user_ids: set[UUID],
    *,
    tenant_id: UUID | None = None,
) -> dict[UUID, str]:
    """Собирает email по списку user_id одним запросом."""
    if not user_ids:
        return {}
    stmt = select(User.id, User.email).where(User.id.in_(user_ids))
    if tenant_id is not None:
        stmt = stmt.where(User.tenant_id == tenant_id)
    result = await db.execute(stmt)
    return {uid: email for uid, email in result.all()}


async def _fetch_user_emails_for_filter(
    db: AsyncSession,
    filter_conditions: list[ColumnElement[bool]],
    *,
    tenant_id: UUID | None = None,
) -> dict[UUID, str]:
    """Email'ы для всех user_id, попадающих под фильтр (для стриминга)."""
    uid_stmt = (
        select(DataAuditLog.user_id)
        .outerjoin(User, DataAuditLog.user_id == User.id)
        .where(and_(*filter_conditions), DataAuditLog.user_id.is_not(None))
        .distinct()
    )
    uid_result = await db.execute(uid_stmt)
    user_ids = {row[0] for row in uid_result.all()}
    return await _collect_user_emails(db, user_ids, tenant_id=tenant_id)


def _normalize_end_date(end_date: datetime) -> datetime:
    """Нормализует end_date до конца дня (включительно)."""
    if end_date.time() == time.min:
        return end_date + timedelta(days=1)
    return end_date


def _format_changes_for_csv(changes: dict[str, Any] | None) -> Tuple[str, str]:
    """Разделяет изменения на 'Было' и 'Стало' для CSV."""
    if not changes:
        return "", ""

    old_lines: list[str] = []
    new_lines: list[str] = []

    for field, val in changes.items():
        if isinstance(val, dict):
            val_dict = cast(dict[str, Any], val)
            old_val = val_dict.get("old")
            new_val = val_dict.get("new")

            # ✅ None / "" → пустая строка в CSV (Excel-ячейка остаётся пустой)
            old_str = str(old_val) if old_val not in (None, "") else ""
            new_str = str(new_val) if new_val not in (None, "") else ""

            old_lines.append(f"{field}: {old_str}" if old_str else f"{field}: ")
            new_lines.append(f"{field}: {new_str}" if new_str else f"{field}: ")
        else:
            val_str = str(val) if val not in (None, "") else ""
            old_lines.append(f"{field}: {val_str}" if val_str else f"{field}:")

    return "\n".join(old_lines), "\n".join(new_lines)


def _build_audit_filter_conditions(
    *,
    is_superadmin: bool,
    tenant_id: UUID,
    entity_type: str | None,
    action: str | None,
    entity_id: UUID | None,
    user_email: str | None,
    start_date: datetime | None,
    end_date: datetime | None,
) -> list[ColumnElement[bool]]:
    """Собирает условия фильтрации для DataAuditLog (общая логика)."""
    filter_conditions: list[ColumnElement[bool]] = []
    if not is_superadmin:
        filter_conditions.append(DataAuditLog.tenant_id == tenant_id)

    if entity_type:
        filter_conditions.append(DataAuditLog.entity_type == entity_type)
    if entity_id:
        filter_conditions.append(DataAuditLog.entity_id == entity_id)
    if action:
        filter_conditions.append(DataAuditLog.action == action)
    if user_email:
        filter_conditions.append(User.email.ilike(f"%{user_email}%"))
    if start_date:
        filter_conditions.append(DataAuditLog.created_at >= start_date)
    if end_date:
        filter_conditions.append(
            DataAuditLog.created_at < _normalize_end_date(end_date)
        )
    return filter_conditions


async def _stream_csv(
    db: AsyncSession,
    filter_conditions: list[ColumnElement[bool]],
    user_emails: dict[UUID, str],
) -> AsyncIterator[str]:
    """Генерирует CSV построчно с колонками Было и Стало."""
    # Заголовок + BOM
    header_buffer = StringIO()
    header_buffer.write("\ufeff")
    header_writer = csv.writer(header_buffer, delimiter=";")
    # ✅ Изменены заголовки для Excel
    header_writer.writerow(
        ["Дата", "Пользователь", "Сущность", "Действие", "Было", "Стало"]
    )
    yield header_buffer.getvalue()

    base_stmt = (
        select(DataAuditLog)
        .outerjoin(User, DataAuditLog.user_id == User.id)
        .where(and_(*filter_conditions))
        .order_by(DataAuditLog.created_at.desc())
    )

    result = await db.stream(base_stmt)
    async for item in result.scalars():
        entity = (
            f"{item.entity_type}: {item.entity_name}"
            if item.entity_name
            else f"{item.entity_type}: {item.entity_id}"
        )

        # ✅ Получаем строки для Было и Стало
        old_text, new_text = _format_changes_for_csv(item.changes)

        row_buffer = StringIO()
        row_writer = csv.writer(row_buffer, delimiter=";")
        row_writer.writerow(
            [
                item.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                (user_emails.get(item.user_id) if item.user_id else None) or "Система",
                entity,
                item.action,
                old_text,
                new_text,
            ]
        )
        yield row_buffer.getvalue()


# ==================================================================
# ЛОГИ ДОСТУПА
# ==================================================================
@router.get(
    "/access",
    response_model=ApiResponse[PaginatedResponse[AuditAccessRead]],
)
async def list_access_audit(
    session: CurrentUser,
    db: DBSession,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, gt=0, le=1000),
) -> ApiResponse[PaginatedResponse[AuditAccessRead]]:
    """Список логов доступа (только админ/суперадмин)."""
    _ensure_audit_access(session)

    is_superadmin = bool(session.is_superadmin)
    tenant_id = session.tenant_id

    if not is_superadmin:
        count_stmt = (
            select(func.count())
            .select_from(AccessAuditLog)
            .where(AccessAuditLog.tenant_id == tenant_id)
        )
    else:
        count_stmt = select(func.count()).select_from(AccessAuditLog)

    count_result = await db.execute(count_stmt)
    total: int = count_result.scalar() or 0

    base_stmt = (
        select(AccessAuditLog)
        .order_by(AccessAuditLog.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    if not is_superadmin:
        base_stmt = base_stmt.where(AccessAuditLog.tenant_id == tenant_id)

    result = await db.execute(base_stmt)
    items = result.scalars().all()

    user_ids: list[UUID | None] = [item.user_id for item in items]
    unique_user_ids = {uid for uid in user_ids if uid is not None}
    user_emails = await _collect_user_emails(
        db,
        unique_user_ids,
        tenant_id=None if is_superadmin else tenant_id,
    )

    audit_items = [
        AuditAccessRead(
            id=item.id,
            tenant_id=item.tenant_id,
            user_id=item.user_id,
            user_email=user_emails.get(item.user_id) if item.user_id else None,
            action=item.action,
            resource=item.resource,
            status=item.status,
            ip_address=item.ip_address,
            created_at=item.created_at,
        )
        for item in items
    ]

    paginated = PaginatedResponse(
        items=audit_items,
        total=total,
        page=(skip // limit) + 1,
        size=limit,
    )

    return ApiResponse(
        success=True,
        message="Логи доступа получены",
        data=paginated,
    )


# ==================================================================
# ЛОГИ ИЗМЕНЕНИЙ ДАННЫХ
# ==================================================================
@router.get(
    "/data",
    response_model=ApiResponse[PaginatedResponse[AuditDataRead]],
)
async def list_data_audit(
    session: CurrentUser,
    db: DBSession,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, gt=0, le=1000),
    entity_type: str | None = None,
    action: str | None = None,
    entity_id: UUID | None = None,
    user_email: str | None = None,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
) -> ApiResponse[PaginatedResponse[AuditDataRead]]:
    """Список изменений данных с пагинацией (только админ/суперадмин)."""
    _ensure_audit_access(session)

    is_superadmin = bool(session.is_superadmin)
    tenant_id = session.tenant_id

    filter_conditions = _build_audit_filter_conditions(
        is_superadmin=is_superadmin,
        tenant_id=tenant_id,
        entity_type=entity_type,
        action=action,
        entity_id=entity_id,
        user_email=user_email,
        start_date=start_date,
        end_date=end_date,
    )

    count_stmt = (
        select(func.count())
        .select_from(DataAuditLog)
        .outerjoin(User, DataAuditLog.user_id == User.id)
        .where(and_(*filter_conditions))
    )
    count_result = await db.execute(count_stmt)
    total: int = count_result.scalar() or 0

    base_stmt = (
        select(DataAuditLog)
        .outerjoin(User, DataAuditLog.user_id == User.id)
        .where(and_(*filter_conditions))
        .order_by(DataAuditLog.created_at.desc())
        .offset(skip)
        .limit(limit)
    )

    result = await db.execute(base_stmt)
    items = result.scalars().all()

    user_ids: list[UUID | None] = [item.user_id for item in items]
    unique_user_ids = {uid for uid in user_ids if uid is not None}
    user_emails = await _collect_user_emails(
        db,
        unique_user_ids,
        tenant_id=None if is_superadmin else tenant_id,
    )

    audit_items = [
        AuditDataRead(
            id=item.id,
            tenant_id=item.tenant_id,
            user_id=item.user_id,
            user_email=user_emails.get(item.user_id) if item.user_id else None,
            entity_type=item.entity_type,
            entity_id=item.entity_id,
            entity_name=item.entity_name,
            action=item.action,
            changes=item.changes,
            created_at=item.created_at,
        )
        for item in items
    ]

    paginated = PaginatedResponse(
        items=audit_items,
        total=total,
        page=(skip // limit) + 1,
        size=limit,
    )

    return ApiResponse(
        success=True,
        message="Данные аудита получены",
        data=paginated,
    )


# ==================================================================
# ЭКСПОРТ В CSV
# ==================================================================
@router.get(
    "/export",
    response_class=StreamingResponse,
)
async def export_data_audit(
    session: CurrentUser,
    db: DBSession,
    entity_type: str | None = None,
    action: str | None = None,
    entity_id: UUID | None = None,
    user_email: str | None = None,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
) -> StreamingResponse:
    """Экспорт изменений данных в CSV (стримингом, только админ/суперадмин)."""
    _ensure_audit_access(session)

    is_superadmin = bool(session.is_superadmin)
    tenant_id = session.tenant_id

    filter_conditions = _build_audit_filter_conditions(
        is_superadmin=is_superadmin,
        tenant_id=tenant_id,
        entity_type=entity_type,
        action=action,
        entity_id=entity_id,
        user_email=user_email,
        start_date=start_date,
        end_date=end_date,
    )

    user_emails = await _fetch_user_emails_for_filter(
        db,
        filter_conditions,
        tenant_id=None if is_superadmin else tenant_id,
    )

    return StreamingResponse(
        _stream_csv(db, filter_conditions, user_emails),
        media_type="text/csv",
        headers={
            "Content-Disposition": "attachment; filename=audit.csv",
            "Content-Type": "text/csv; charset=utf-8",
        },
    )
