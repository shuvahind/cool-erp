"""backend/app/core/audit/service.py"""

import uuid
from typing import Any, Mapping, List, cast, Dict, Optional

from sqlalchemy import select, inspect
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit.models import AccessAuditLog, DataAuditLog
from app.core.users.models import UserModel
from app.core.sections.models import SectionModel
from app.core.tenants.models import TenantModel
# ✅ Импортируем модель типа номенклатуры для получения названия
from app.modules.sales.item_types.models import SalesItemTypeModel


IGNORED_FIELDS = {"user_names", "section_names"}

PRETTY_NAMES = {
    # ✅ Роли
    "tenant_id": "Организация",
    "user_ids": "Пользователи",
    "section_ids": "Разделы",
    "name": "Название",
    "description": "Описание",
    "permissions": "Полномочия",
    # ✅ Пользователи
    "password": "Пароль",
    "tags": "Теги",  
    # ✅ Заметки
    "title": "Заголовок",
    "content": "Содержание",
    "or_tags": "Теги (ИЛИ)",
    "and_tags": "Теги (И)",
    "doc_date": "Дата документа",
    "doc_number": "Номер документа",
    "doc_status": "Статус документа",
    "section_id": "Раздел",
    # ✅ Склады
    "code": "Код",
    "warehouse_type": "Тип склада",
    # ✅ ТОВАРЫ 
    "item_type_id": "Тип номенклатуры",
    "base_uom": "Единица измерения",
    # ✅ Авторство
    "author_id": "Автор",
    "created_by_user_id": "Создал",
}


async def _get_users_string(
    db: AsyncSession, user_ids: List[uuid.UUID]
) -> Optional[str]:
    if not user_ids:
        return None
    stmt = select(UserModel.email).where(UserModel.id.in_(user_ids))
    result = await db.execute(stmt)
    emails = [email for email, in result.all()]
    return ", ".join(emails) if emails else None


async def _get_sections_string(
    db: AsyncSession, section_ids: List[uuid.UUID]
) -> Optional[str]:
    if not section_ids:
        return None
    stmt = select(SectionModel.name).where(SectionModel.id.in_(section_ids))
    result = await db.execute(stmt)
    names = [name for name, in result.all()]
    return ", ".join(names) if names else None


async def _get_tenant_string(
    db: AsyncSession, tenant_id: uuid.UUID
) -> Optional[str]:
    if not tenant_id:
        return None
    stmt = select(TenantModel.name).where(TenantModel.id == tenant_id)
    result = await db.execute(stmt)
    name = result.scalar_one_or_none()
    return name or str(tenant_id)


# ✅ Новая функция для получения названия типа номенклатуры
async def _get_item_type_string(
    db: AsyncSession, item_type_id: uuid.UUID
) -> Optional[str]:
    if not item_type_id:
        return None
    stmt = select(SalesItemTypeModel.name).where(SalesItemTypeModel.id == item_type_id)
    result = await db.execute(stmt)
    name = result.scalar_one_or_none()
    return name or str(item_type_id)


def _format_tags_string(tags: Optional[List[str]]) -> Optional[str]:
    """Склеивает список тегов в строку через запятую."""
    if not tags:
        return None
    return ", ".join(tags)


async def _format_create_value(
    db: AsyncSession, key: str, value: Any
) -> Optional[str]:
    if value is None or value == []:
        return None
    if key == "tenant_id":
        return await _get_tenant_string(db, value)
    if key == "user_ids":
        return await _get_users_string(db, cast(List[uuid.UUID], value))
    if key == "section_ids":
        return await _get_sections_string(db, cast(List[uuid.UUID], value))
    
    # ✅ Красиво выводим автора и создателя
    if key in ("author_id", "created_by_user_id") and value:
        return await _get_users_string(db, [cast(uuid.UUID, value)])

    # ✅ Красиво выводим один раздел по ID
    if key == "section_id" and value:
        return await _get_sections_string(db, [cast(uuid.UUID, value)])

    # ✅ Красиво выводим тип номенклатуры по ID
    if key == "item_type_id" and value:
        return await _get_item_type_string(db, cast(uuid.UUID, value))

    # ✅ Обработка тегов при СОЗДАНИИ (tags, or_tags, and_tags)
    if key in ("tags", "or_tags", "and_tags") and isinstance(value, list):
        return _format_tags_string(cast(List[str], value))

    # ✅ Обработка полномочий при СОЗДАНИИ
    if key == "permissions" and isinstance(value, list):
        val_list = cast(List[Any], value)
        res: List[str] = []
        for p in val_list:
            doctype = "неизвестно"
            rights: List[str] = []

            if isinstance(p, dict):
                p_dict = cast(Dict[str, Any], p)
                doctype = str(p_dict.get("doctype_name", "неизвестно"))
                if p_dict.get("full_access"):
                    rights.append("Полный")
                if p_dict.get("author"):
                    rights.append("Автор")
                if p_dict.get("reader"):
                    rights.append("Чтение")
                if p_dict.get("editor"):
                    rights.append("Редактор")
                if p_dict.get("can_delete"):
                    rights.append("Удаление")
            elif hasattr(p, "doctype_name"):
                doctype = str(getattr(p, "doctype_name"))
                if getattr(p, "full_access", False):
                    rights.append("Полный")
                if getattr(p, "author", False):
                    rights.append("Автор")
                if getattr(p, "reader", False):
                    rights.append("Чтение")
                if getattr(p, "editor", False):
                    rights.append("Редактор")
                if getattr(p, "can_delete", False):
                    rights.append("Удаление")

            if rights:
                res.append(f"[Добавлен] {doctype} ({', '.join(rights)})")
            else:
                res.append(f"[Добавлен] {doctype} (нет прав)")

        return "; ".join(res) if res else None

    if key == "permissions" and isinstance(value, str):
        return value

    if isinstance(value, bool):
        return "Да" if value else "Нет"
    return str(value)


async def log_data_create(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    entity_type: str,
    entity_id: uuid.UUID,
    entity_name: str | None,
    changes: Mapping[str, Any] | None = None,
) -> None:
    formatted_changes: dict[str, dict[str, Optional[str]]] = {}
    if changes:
        for key, value in changes.items():
            if key in IGNORED_FIELDS or value is None or value == []:
                continue
            pretty_key = PRETTY_NAMES.get(key, key)
            formatted_changes[pretty_key] = {
                "old": None,
                "new": await _format_create_value(db, key, value),
            }
    if not formatted_changes:
        return
    db.add(
        DataAuditLog(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            user_id=user_id,
            entity_type=entity_type,
            entity_id=entity_id,
            entity_name=entity_name,
            action="create",
            changes=formatted_changes,
        )
    )


async def log_data_update(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    entity_type: str,
    entity_id: uuid.UUID,
    entity_name: str | None,
    old_values: Mapping[str, Any],
    new_values: Mapping[str, Any],
) -> None:
    changes: dict[str, dict[str, Optional[str]]] = {}
    for field, new_value in new_values.items():
        if field in IGNORED_FIELDS or field not in old_values:
            continue
        old_value = old_values[field]

        # ✅ Сравниваем списки через set()
        if field in ("user_ids", "section_ids", "tags", "or_tags", "and_tags"):
            old_set = set(old_value) if old_value else set()
            new_set = set(new_value) if new_value else set()
            if old_set == new_set:
                continue
        else:
            if old_value == new_value:
                continue

        pretty_key = PRETTY_NAMES.get(field, field)
        old_str: Optional[str] = None
        new_str: Optional[str] = None

        if field == "tenant_id":
            old_str = await _get_tenant_string(db, old_value) if old_value else None
            new_str = await _get_tenant_string(db, new_value) if new_value else None
        elif field == "user_ids":
            old_str = await _get_users_string(db, old_value) if old_value else None
            new_str = await _get_users_string(db, new_value) if new_value else None
        elif field == "section_ids":
            old_str = (
                await _get_sections_string(db, old_value) if old_value else None
            )
            new_str = (
                await _get_sections_string(db, new_value) if new_value else None
            )
        elif field == "section_id":
            old_str = await _get_sections_string(db, [old_value]) if old_value else None
            new_str = await _get_sections_string(db, [new_value]) if new_value else None

        # ✅ Красиво выводим тип номенклатуры при ОБНОВЛЕНИИ
        elif field == "item_type_id":
            old_str = await _get_item_type_string(db, old_value) if old_value else None
            new_str = await _get_item_type_string(db, new_value) if new_value else None
        
        # ✅ Красиво выводим автора при ОБНОВЛЕНИИ
        elif field in ("author_id", "created_by_user_id"):
            old_str = await _get_users_string(db, [old_value]) if old_value else None
            new_str = await _get_users_string(db, [new_value]) if new_value else None

        elif field == "permissions" and isinstance(new_value, str):
            old_str = str(old_value) if old_value else None
            new_str = str(new_value) if new_value else None
        
        # ✅ Обработка тегов при ОБНОВЛЕНИИ
        elif field in ("tags", "or_tags", "and_tags"):
            old_str = _format_tags_string(cast(List[str], old_value)) if old_value else None
            new_str = _format_tags_string(cast(List[str], new_value)) if new_value else None

        elif isinstance(new_value, list):
            old_list = cast(List[Any], old_value) if old_value else []
            new_list = cast(List[Any], new_value)
            old_str = f"[{len(old_list)} шт.]" if old_list else None
            new_str = f"[{len(new_list)} шт.]" if new_list else None
        else:
            old_str = str(old_value) if old_value is not None else None
            new_str = str(new_value) if new_value is not None else None
            if old_str and "object at 0x" in old_str:
                old_str = "объект"
            if new_str and "object at 0x" in new_str:
                new_str = "объект"

        changes[pretty_key] = {"old": old_str, "new": new_str}

    if not changes:
        return
    db.add(
        DataAuditLog(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            user_id=user_id,
            entity_type=entity_type,
            entity_id=entity_id,
            entity_name=entity_name,
            action="update",
            changes=changes,
        )
    )

async def _extract_snapshot(obj: Any) -> dict[str, Any]:
    """Универсальный сборщик снимка модели для аудита удаления."""
    ignored = {
        "id", "version", "created_at", "updated_at", 
        "created_by_user_id", "updated_by_user_id", 
        "deleted_at", "deleted_by_user_id",
        "editing_by_user_id", "editing_since", "password", "section_names",
    }
    changes = {}
    # Проходим по колонкам модели SQLAlchemy
    for column in inspect(obj).mapper.column_attrs:
        if column.key in ignored:
            continue
        val = getattr(obj, column.key)
        if val is not None:
            changes[column.key] = {"old": val, "new": ""}
    return changes

async def log_data_delete_snapshot(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    entity_type: str,
    entity_id: uuid.UUID,
    entity_name: str | None,
    obj: Any,
    extra_changes: dict[str, Any] | None = None,  # ✅ ДОБАВЛЕНО
) -> None:
    raw_changes = await _extract_snapshot(obj)
    
    # ✅ Сливаем автоснимок с ручными связями
    if extra_changes:
        raw_changes.update(extra_changes)

    formatted_changes: dict[str, dict[str, Optional[str]]] = {}

    for key, val_dict in raw_changes.items():
        old_val = val_dict.get("old")
        formatted_old = await _format_create_value(db, key, old_val) if old_val is not None else None
        
        if formatted_old is not None:
            pretty_key = PRETTY_NAMES.get(key, key)
            formatted_changes[pretty_key] = {
                "old": formatted_old,
                "new": None,
            }

    db.add(
        DataAuditLog(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            user_id=user_id,
            entity_type=entity_type,
            entity_id=entity_id,
            entity_name=entity_name,
            action="delete",
            changes=formatted_changes if formatted_changes else None,
        )
    )


async def log_access(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID | None,
    action: str,
    resource: str,
    status: str = "success",
    ip_address: str | None = None,
) -> None:
    db.add(
        AccessAuditLog(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            user_id=user_id,
            action=action,
            resource=resource,
            status=status,
            ip_address=ip_address,
        )
    )