"""PostgreSQL storage for CRM stages."""

import logging
from datetime import datetime
from typing import Optional

from app.models.crm import CRMStage
from app.storage.postgres import get_pool
from app.utils.datetime_utils import utc_now

logger = logging.getLogger(__name__)


def _row_to_stage(row: dict) -> CRMStage:
    return CRMStage(
        id=str(row["id"]),
        name=row["name"],
        color=row["color"],
        position=row["position"],
        is_default=row["is_default"],
        created_at=row["created_at"],
    )


class PostgresCRMStorage:
    """CRUD operations for CRM stages."""

    async def list_stages(self) -> list[CRMStage]:
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM crm_stages ORDER BY position ASC, created_at ASC"
            )
        return [_row_to_stage(r) for r in rows]

    async def get_stage(self, stage_id: str) -> Optional[CRMStage]:
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM crm_stages WHERE id = $1", stage_id
            )
        return _row_to_stage(row) if row else None

    async def create_stage(self, name: str, color: str) -> CRMStage:
        pool = await get_pool()
        async with pool.acquire() as conn:
            max_pos = await conn.fetchval(
                "SELECT COALESCE(MAX(position), -1) FROM crm_stages"
            )
            row = await conn.fetchrow(
                """
                INSERT INTO crm_stages (name, color, position, is_default)
                VALUES ($1, $2, $3, FALSE)
                RETURNING *
                """,
                name,
                color,
                max_pos + 1,
            )
        return _row_to_stage(row)

    async def update_stage(
        self,
        stage_id: str,
        name: Optional[str] = None,
        color: Optional[str] = None,
        position: Optional[int] = None,
    ) -> Optional[CRMStage]:
        updates = []
        params: list = []
        i = 1

        if name is not None:
            updates.append(f"name = ${i}")
            params.append(name)
            i += 1
        if color is not None:
            updates.append(f"color = ${i}")
            params.append(color)
            i += 1
        if position is not None:
            updates.append(f"position = ${i}")
            params.append(position)
            i += 1

        if not updates:
            return await self.get_stage(stage_id)

        params.append(stage_id)
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                f"UPDATE crm_stages SET {', '.join(updates)} WHERE id = ${i} RETURNING *",
                *params,
            )
        return _row_to_stage(row) if row else None

    async def delete_stage(self, stage_id: str) -> bool:
        """Delete stage. Returns False if stage has conversations assigned."""
        pool = await get_pool()
        async with pool.acquire() as conn:
            count = await conn.fetchval(
                "SELECT COUNT(*) FROM conversations WHERE crm_stage_id = $1", stage_id
            )
            if count > 0:
                return False
            result = await conn.execute(
                "DELETE FROM crm_stages WHERE id = $1 AND is_default = FALSE", stage_id
            )
        return result == "DELETE 1"

    async def get_stage_counts(
        self, start_date: Optional[datetime] = None, end_date: Optional[datetime] = None
    ) -> list[dict]:
        """Return count of conversations per stage within optional date range."""
        pool = await get_pool()
        async with pool.acquire() as conn:
            if start_date and end_date:
                rows = await conn.fetch(
                    """
                    SELECT s.id, s.name, s.color, s.position,
                           COUNT(c.conversation_id) AS count
                    FROM crm_stages s
                    LEFT JOIN conversations c
                        ON c.crm_stage_id = s.id
                       AND c.created_at >= $1
                       AND c.created_at <= $2
                    GROUP BY s.id, s.name, s.color, s.position
                    ORDER BY s.position ASC
                    """,
                    start_date,
                    end_date,
                )
            else:
                rows = await conn.fetch(
                    """
                    SELECT s.id, s.name, s.color, s.position,
                           COUNT(c.conversation_id) AS count
                    FROM crm_stages s
                    LEFT JOIN conversations c ON c.crm_stage_id = s.id
                    GROUP BY s.id, s.name, s.color, s.position
                    ORDER BY s.position ASC
                    """
                )
        return [
            {
                "id": str(r["id"]),
                "name": r["name"],
                "color": r["color"],
                "position": r["position"],
                "count": r["count"],
            }
            for r in rows
        ]
