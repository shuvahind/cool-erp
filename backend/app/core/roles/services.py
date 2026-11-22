"""backend/app/core/roles/services.py"""

import logging
import uuid
from typing import Any, List, Dict, Tuple, cast

from fastapi import HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import service as audit_service
from app.core.permissions.models import PermissionModel
from app.core.permissions.crud import crud_permission
from app.core.permissions.schemas import (
    PermissionCreateSchema,
    PermissionUpdateSchema,
)
from app.core.roles.models import RoleModel
from app.core.roles.crud import crud_role
from app.core.roles.schemas import (
    RoleSaveSchema,
    RoleCreateSchema,
    RoleUpdateSchema,
)
from app.core.users.models import UserModel
from app.core.sections.models import SectionModel

logger = logging.getLogger(__name__)


class RoleService:
    """
    Сервис для управления ролями с их связями (полномочия и пользователи).
    Обеспечивает атомарность операций в рамках одной транзакции.
    """

    # ================================================================
    # ✅ ВСПОМОГАТЕЛЬНЫЙ МЕТОД (перенесен из роутера)
    # ================================================================
    def format_permissions_for_audit(
        self, old_perms: Any, new_perms: Any
    ) -> Tuple[str, str]:
        """Вычисляет разницу в полномочиях и возвращает строки для аудита."""

        def extract_dict(perms: Any) -> Dict[str, List[str]]:
            res: Dict[str, List[str]] = {}
            if not perms:
                return res
            for p in perms:
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

                res[doctype] = rights
            return res

        old_dict = extract_dict(old_perms)
        new_dict = extract_dict(new_perms)

        old_parts: List[str] = []
        new_parts: List[str] = []
        changes_found = False

        all_doctypes = set(old_dict.keys()) | set(new_dict.keys())

        for doctype in all_doctypes:
            old_r = set(old_dict.get(doctype, []))
            new_r = set(new_dict.get(doctype, []))

            if old_r == new_r:
                continue

            changes_found = True

            old_parts.append(f"{doctype} ({', '.join(old_r) if old_r else '-'})")

            if old_r and not new_r:
                new_parts.append(f"[Удалено] {doctype} ({', '.join(old_r)})")
            elif not old_r and new_r:
                new_parts.append(f"[Добавлен] {doctype} ({', '.join(new_r)})")
            else:
                added = new_r - old_r
                removed = old_r - new_r

                notes: List[str] = []
                if added:
                    notes.append(f"[Добавлен] {doctype} ({', '.join(added)})")
                if removed:
                    notes.append(f"[Удалено] {doctype} ({', '.join(removed)})")
                new_parts.append(", ".join(notes))

        if not changes_found:
            return "", ""

        return ", ".join(old_parts), ", ".join(new_parts)

    # ================================================================
    # ✅ МЕТОД: УДАЛЕНИЕ С АУДИТОМ 
    # ================================================================
    async def delete(
        self,
        db: AsyncSession,
        *,
        role_id: uuid.UUID,
        current_session: Any,
    ) -> RoleModel:
        is_superadmin = bool(current_session.is_superadmin)

        existing_role = await crud_role.get(
            db, item_id=role_id,
            current_tenant_id=current_session.tenant_id,
            is_superadmin=is_superadmin,
        )
        if not existing_role:
            raise ValueError("Роль не найдена")

        # ✅ Собираем ТОЛЬКО СВЯЗИ (скалярные поля соберет snapshot)
        old_perms_stmt = select(PermissionModel).where(PermissionModel.role_id == role_id)
        old_perms_result = await db.execute(old_perms_stmt)
        old_perms = list(old_perms_result.scalars().all())

        extra_changes: dict[str, Any] = {}
        
        if old_perms:
            perms_str, _ = self.format_permissions_for_audit(old_perms, [])
            if perms_str:
                extra_changes["permissions"] = {"old": perms_str, "new": ""}
                
        users_list = [u.email for u in existing_role.users] if existing_role.users else []
        if users_list:
            # ✅ Передаем ключ "user_ids", чтобы отработал _format_create_value
            # Но так как это уже строка, _format_create_value просто вернет её.
            # Лучше передать как строку, но тогда отработает PRETTY_NAMES для "user_ids".
            extra_changes["user_ids"] = {"old": users_list, "new": ""}

        # Очищаем роль из массивов role_ids у всех пользователей
        users_stmt = select(UserModel).where(
            UserModel.role_ids.isnot(None),
            UserModel.role_ids.contains([role_id]),
        )
        users_result = await db.execute(users_stmt)
        for user in users_result.scalars().all():
            if user.role_ids:
                user.role_ids = [rid for rid in user.role_ids if rid != role_id]

        deleted_role = await crud_role.delete(
            db, item_id=role_id,
            current_tenant_id=current_session.tenant_id,
            is_superadmin=is_superadmin,
        )

        # ✅ Передаем extra_changes в snapshot
        await audit_service.log_data_delete_snapshot(
            db,
            tenant_id=deleted_role.tenant_id,
            user_id=current_session.id,
            entity_type="role",
            entity_id=deleted_role.id,
            entity_name=deleted_role.name,
            obj=existing_role,
            extra_changes=extra_changes,  # <--- вот они, связи!
        )

        return deleted_role

    # ================================================================
    # МЕТОД: СОХРАНЕНИЕ (агрегированный)
    # ================================================================
    async def save_role(
        self,
        db: AsyncSession,
        data: RoleSaveSchema,
        current_tenant_id: uuid.UUID,
        is_superadmin: bool,
        role_id: uuid.UUID | None = None,
    ) -> RoleModel:
        logger.info(
            "[save_role] START: role_id=%s, user_ids=%s, permissions_count=%s",
            role_id,
            data.user_ids,
            len(data.permissions) if data.permissions else 0,
        )

        # ============================================================
        # 0. ЦЕЛЕВАЯ ОРГАНИЗАЦИЯ РОЛИ — безусловное присваивание
        # ============================================================
        target_role_tenant_id: uuid.UUID = (
            data.tenant_id if data.tenant_id is not None else current_tenant_id  # type: ignore
        )

        if role_id is not None:
            existing_role = await crud_role.get(
                db,
                item_id=role_id,
                current_tenant_id=current_tenant_id,
                is_superadmin=is_superadmin,
            )
            if existing_role is None:
                raise HTTPException(status_code=404, detail="Роль не найдена")

            target_role_tenant_id = existing_role.tenant_id

        # ============================================================
        # 0.1. ВАЛИДАЦИЯ: разделы должны принадлежать организации роли
        # ============================================================
        if data.section_ids:
            if role_id:
                role_for_check = await crud_role.get(
                    db,
                    item_id=role_id,
                    current_tenant_id=current_tenant_id,
                    is_superadmin=is_superadmin,
                )
                if not role_for_check:
                    raise HTTPException(status_code=404, detail="Роль не найдена")
                target_role_tenant_id = role_for_check.tenant_id
            else:
                target_role_tenant_id = data.tenant_id or current_tenant_id

            sections_stmt = select(SectionModel).where(
                SectionModel.id.in_(data.section_ids)
            )
            sections_result = await db.execute(sections_stmt)
            found_sections: list[SectionModel] = list(sections_result.scalars().all())
            found_section_ids: set[uuid.UUID] = {s.id for s in found_sections}

            missing_ids: set[uuid.UUID] = set(data.section_ids) - found_section_ids
            if missing_ids:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        "Разделы не найдены: "
                        + ", ".join(str(mid) for mid in missing_ids)
                    ),
                )

            invalid_section_names: list[str] = []
            for section in found_sections:
                if section.tenant_id is None:
                    continue
                if section.tenant_id != target_role_tenant_id:
                    invalid_section_names.append(section.name)

            if invalid_section_names:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        "Попытка добавить для Роли Раздел из другой Организации: "
                        + ", ".join(invalid_section_names)
                    ),
                )

            logger.info(
                "[save_role] Sections validated: %d sections OK for tenant %s",
                len(found_sections),
                target_role_tenant_id,
            )

        # ============================================================
        # 0.2. Проверка уникальности названия роли
        # ============================================================
        if await crud_role.check_name_exists(
            db,
            name=data.name,
            tenant_id=target_role_tenant_id,
            exclude_role_id=role_id,
        ):
            raise HTTPException(
                status_code=400,
                detail=f"Роль с названием '{data.name}' уже существует в этой организации",
            )

        # ============================================================
        # 1. Создаем или обновляем саму роль
        # ============================================================
        if role_id:
            existing_role = await crud_role.get(
                db,
                item_id=role_id,
                current_tenant_id=current_tenant_id,
                is_superadmin=is_superadmin,
            )
            if not existing_role:
                raise HTTPException(status_code=404, detail="Роль не найдена")

            if (
                is_superadmin
                and data.tenant_id
                and data.tenant_id != existing_role.tenant_id
            ):
                assigned = await self._check_role_assignments(db, existing_role)
                if assigned:
                    raise HTTPException(
                        status_code=400,
                        detail=(
                            f"Для роли '{existing_role.name}' уже назначены: "
                            f"{', '.join(assigned)}. "
                            f"Нельзя изменить организацию. Сначала удалите все назначения."
                        ),
                    )

            if is_superadmin and data.tenant_id:
                update_data = RoleUpdateSchema(
                    name=data.name,
                    description=data.description,
                    section_ids=data.section_ids,
                    section_names=data.section_names,
                    tenant_id=data.tenant_id,
                )
            else:
                update_data = RoleUpdateSchema(
                    name=data.name,
                    description=data.description,
                    section_ids=data.section_ids,
                    section_names=data.section_names,
                )

            role = await crud_role.update(
                db,
                item_id=role_id,
                data=update_data,
                current_tenant_id=current_tenant_id,
                is_superadmin=is_superadmin,
            )
        else:
            create_data = RoleCreateSchema(
                name=data.name,
                description=data.description,
                tenant_id=data.tenant_id,
                section_ids=data.section_ids,
                section_names=data.section_names,
            )
            role = await crud_role.create(
                db,
                data=create_data,
                current_tenant_id=current_tenant_id,
                is_superadmin=is_superadmin,
            )

        logger.info("[save_role] Role saved: id=%s, name=%s", role.id, role.name)

        # ============================================================
        # 2. Синхронизация полномочий (Permissions)
        # ============================================================
        stmt = select(PermissionModel).where(PermissionModel.role_id == role.id)
        if not is_superadmin:
            stmt = stmt.where(PermissionModel.tenant_id == current_tenant_id)
        result = await db.execute(stmt)
        existing_permissions = {p.id: p for p in result.scalars().all()}
        incoming_perm_ids: set[uuid.UUID] = set()

        target_tenant_id: uuid.UUID = role.tenant_id

        if data.permissions:
            for perm_data in data.permissions:
                if perm_data.id and perm_data.id in existing_permissions:
                    perm_dict = perm_data.model_dump(exclude={"id", "tenant_id"})
                    perm_dict["role_id"] = role.id
                    perm_dict["role_name"] = role.name
                    update_schema = PermissionUpdateSchema(**perm_dict)

                    await crud_permission.update_permission(
                        db,
                        item_id=perm_data.id,
                        obj_in=update_schema,
                        current_tenant_id=target_tenant_id,
                        is_superadmin=is_superadmin,
                    )
                    incoming_perm_ids.add(perm_data.id)
                else:
                    perm_dict = perm_data.model_dump(exclude={"id", "tenant_id"})
                    perm_dict["role_id"] = role.id
                    perm_dict["role_name"] = role.name
                    perm_dict["tenant_id"] = target_tenant_id

                    safe_perm_data = PermissionCreateSchema(**perm_dict)

                    new_perm = await crud_permission.create_permission(
                        db,
                        obj_in=safe_perm_data,
                        current_tenant_id=target_tenant_id,
                        is_superadmin=is_superadmin,
                    )
                    incoming_perm_ids.add(new_perm.id)

        perms_to_delete = set(existing_permissions.keys()) - incoming_perm_ids
        for perm_id in perms_to_delete:
            await crud_permission.delete_permission(
                db,
                item_id=perm_id,
                current_tenant_id=target_tenant_id,
                is_superadmin=is_superadmin,
            )

        logger.info(
            "[save_role] Permissions synced: incoming=%d, deleted=%d",
            len(incoming_perm_ids),
            len(perms_to_delete),
        )

        # ============================================================
        # 3. Синхронизация пользователей (Users)
        # ============================================================
        if data.user_ids is not None:
            logger.info(
                "[save_role] Syncing users: target_user_ids=%s, role_id=%s",
                data.user_ids,
                role.id,
            )

            target_user_ids: set[uuid.UUID] = set(data.user_ids)

            tenant_for_users = role.tenant_id
            stmt = select(UserModel).where(UserModel.tenant_id == tenant_for_users)
            result = await db.execute(stmt)
            all_tenant_users = result.scalars().all()

            logger.info(
                "[save_role] Loaded %d users for tenant %s",
                len(all_tenant_users),
                tenant_for_users,
            )

            changed_count = 0
            for user in all_tenant_users:
                current_role_ids: set[uuid.UUID] = set(user.role_ids or [])
                updated = False

                if user.id in target_user_ids:
                    if role.id not in current_role_ids:
                        current_role_ids.add(role.id)
                        updated = True
                else:
                    if role.id in current_role_ids:
                        current_role_ids.discard(role.id)
                        updated = True

                if updated:
                    user.role_ids = list(current_role_ids)
                    changed_count += 1

                    logger.info(
                        "[save_role] User %s (%s) updated: role_ids=%s",
                        user.id,
                        user.name,
                        user.role_ids,
                    )

            logger.info(
                "[save_role] Users sync complete: %d users changed",
                changed_count,
            )

        # ============================================================
        # 4. Финальный flush (commit — в роутере)
        # ============================================================
        await db.flush()
        logger.info("[save_role] Transaction flushed successfully")

        await db.refresh(role, attribute_names=["permissions"])
        logger.info("[save_role] SUCCESS: role=%s", role.id)
        return role

    async def _check_role_assignments(
        self, db: AsyncSession, role: RoleModel
    ) -> list[str]:
        """
        Проверяет наличие назначений для роли.
        Возвращает список типов назначений: ["Разделы", "Полномочия", "Пользователи"].
        """
        assigned: list[str] = []

        if role.section_ids:
            assigned.append("Разделы")

        perm_count_stmt = (
            select(func.count())
            .select_from(PermissionModel)
            .where(PermissionModel.role_id == role.id)
        )
        perm_count = (await db.execute(perm_count_stmt)).scalar() or 0
        if perm_count > 0:
            assigned.append("Полномочия")

        user_count_stmt = (
            select(func.count())
            .select_from(UserModel)
            .where(
                UserModel.role_ids.isnot(None),
                UserModel.role_ids.contains([role.id]),
            )
        )
        user_count = (await db.execute(user_count_stmt)).scalar() or 0
        if user_count > 0:
            assigned.append("Пользователи")

        logger.info(
            "[_check_role_assignments] role=%s, assigned=%s",
            role.id,
            assigned,
        )
        return assigned


role_service = RoleService()