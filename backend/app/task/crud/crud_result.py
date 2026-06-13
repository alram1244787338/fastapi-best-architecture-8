from collections.abc import Sequence
from datetime import date, datetime

import sqlalchemy as sa
from sqlalchemy import Select, cast, delete, func, select
from sqlalchemy.engine.row import Row
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy_crud_plus import CRUDPlus

from backend.app.task.model import TaskResult


class CRUDTaskResult(CRUDPlus[TaskResult]):
    """任务结果数据库操作类"""

    async def get(self, db: AsyncSession, pk: int) -> TaskResult | None:
        """
        获取任务结果详情

        :param db: 数据库会话
        :param pk: 任务 ID
        :return:
        """
        return await self.select_model(db, pk)

    async def get_select(self, name: str | None, task_id: str | None) -> Select:
        """
        获取任务结果列表查询表达式

        :param name: 任务名称
        :param task_id: 任务 ID
        :return:
        """
        filters = {}

        if name is not None:
            filters['name__like'] = f'%{name}%'
        if task_id is not None:
            filters['task_id'] = task_id

        return await self.select_order('id', 'desc', **filters)

    async def delete(self, db: AsyncSession, pks: list[int]) -> int:
        """
        批量删除任务结果

        :param db: 数据库会话
        :param pks: 任务结果 ID 列表
        :return:
        """
        return await self.delete_model_by_column(db, allow_multiple=True, id__in=pks)

    def _build_conditions(
        self,
        name: str | None = None,
        task_id: str | None = None,
        status: str | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list:
        """
        构建通用过滤条件列表

        :param name: 任务名称（模糊匹配）
        :param task_id: 任务 ID（精确匹配）
        :param status: 执行状态（精确匹配）
        :param start_date: 起始日期（含）
        :param end_date: 截止日期（含）
        :return: SQLAlchemy 过滤条件列表
        """
        conditions = []
        if name is not None:
            conditions.append(self.model.name.like(f'%{name}%'))
        if task_id is not None:
            conditions.append(self.model.task_id == task_id)
        if status is not None:
            conditions.append(self.model.status == status)
        if start_date is not None:
            start_dt = datetime(start_date.year, start_date.month, start_date.day)
            conditions.append(self.model.date_done >= start_dt)
        if end_date is not None:
            # 包含截止日期当天 23:59:59.999999
            end_dt = datetime(end_date.year, end_date.month, end_date.day, 23, 59, 59, 999999)
            conditions.append(self.model.date_done <= end_dt)
        return conditions

    async def get_stats(
        self,
        db: AsyncSession,
        name: str | None = None,
        task_id: str | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[Row]:
        """
        按状态聚合统计任务结果数量

        :param db: 数据库会话
        :param name: 任务名称
        :param task_id: 任务 ID
        :param start_date: 起始日期
        :param end_date: 截止日期
        :return: [(status, count), ...] 聚合结果
        """
        stmt = (
            select(self.model.status, func.count(self.model.id).label('count'))
            .where(*self._build_conditions(name, task_id, start_date=start_date, end_date=end_date))
            .group_by(self.model.status)
        )
        result = await db.execute(stmt)
        return result.all()

    async def get_daily_trend(
        self,
        db: AsyncSession,
        name: str | None = None,
        task_id: str | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[Row]:
        """
        按日期 + 状态聚合每日执行趋势

        :param db: 数据库会话
        :param name: 任务名称
        :param task_id: 任务 ID
        :param start_date: 起始日期
        :param end_date: 截止日期
        :return: [(done_date, status, count), ...] 聚合结果
        """
        done_date = cast(self.model.date_done, sa.Date).label('done_date')
        stmt = (
            select(done_date, self.model.status, func.count(self.model.id).label('count'))
            .where(*self._build_conditions(name, task_id, start_date=start_date, end_date=end_date))
            .group_by(done_date, self.model.status)
            .order_by(done_date)
        )
        result = await db.execute(stmt)
        return result.all()

    async def get_recent_executions(
        self,
        db: AsyncSession,
        name: str | None = None,
        task_id: str | None = None,
        limit: int = 10,
    ) -> Sequence[TaskResult]:
        """
        获取最近 N 次执行记录

        :param db: 数据库会话
        :param name: 任务名称
        :param task_id: 任务 ID
        :param limit: 返回条数上限
        :return: 最近执行记录列表
        """
        conditions = self._build_conditions(name, task_id)
        stmt = (
            select(self.model)
            .where(*conditions)
            .order_by(self.model.id.desc())
            .limit(limit)
        )
        result = await db.execute(stmt)
        return result.scalars().all()

    async def cleanup_by_conditions(
        self,
        db: AsyncSession,
        name: str | None = None,
        task_id: str | None = None,
        status: str | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> int:
        """
        按条件批量删除任务结果

        :param db: 数据库会话
        :param name: 任务名称（模糊匹配）
        :param task_id: 任务 ID
        :param status: 执行状态
        :param start_date: 起始日期
        :param end_date: 截止日期
        :return: 删除的记录数
        """
        conditions = self._build_conditions(name, task_id, status, start_date, end_date)
        stmt = delete(self.model).where(*conditions)
        result = await db.execute(stmt)
        return result.rowcount


task_result_dao: CRUDTaskResult = CRUDTaskResult(TaskResult)
