from collections import defaultdict
from datetime import date, timedelta
from typing import Any

from celery import states
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.task.crud.crud_result import task_result_dao
from backend.app.task.model import TaskResult
from backend.app.task.schema.result import (
    CleanupTaskResultParam,
    CleanupTaskResultResult,
    DeleteTaskResultParam,
    TaskResultDailyTrend,
    TaskResultRecentExecution,
    TaskResultStatsData,
    TaskResultStatsQuery,
)
from backend.common.exception import errors
from backend.common.pagination import paging_data
from backend.utils.timezone import timezone


class TaskResultService:
    @staticmethod
    async def get(*, db: AsyncSession, pk: int) -> TaskResult:
        """
        获取任务结果详情

        :param db: 数据库会话
        :param pk: 任务 ID
        :return:
        """

        result = await task_result_dao.get(db, pk)
        if not result:
            raise errors.NotFoundError(msg='任务结果不存在')
        return result

    @staticmethod
    async def get_list(*, db: AsyncSession, name: str | None, task_id: str | None) -> dict[str, Any]:
        """
        获取任务结果列表

        :param db: 数据库会话
        :param name: 任务名称
        :param task_id: 任务 ID
        :return:
        """
        result_select = await task_result_dao.get_select(name, task_id)
        return await paging_data(db, result_select)

    @staticmethod
    async def delete(*, db: AsyncSession, obj: DeleteTaskResultParam) -> int:
        """
        批量删除任务结果

        :param db: 数据库会话
        :param obj: 任务结果 ID 列表
        :return:
        """

        count = await task_result_dao.delete(db, obj.pks)
        return count

    @staticmethod
    async def get_stats(*, db: AsyncSession, query: TaskResultStatsQuery) -> TaskResultStatsData:
        """
        获取任务结果统计数据

        按任务名/任务 ID + 时间范围聚合统计成功、失败、待处理数量及成功率，
        同时返回每日执行趋势和最近 N 次执行摘要。

        :param db: 数据库会话
        :param query: 统计查询参数
        :return: 任务结果统计数据
        """
        today = timezone.now().date()
        start_date = query.start_date or (today - timedelta(days=6))
        end_date = query.end_date or today

        # 1. 按状态聚合统计
        status_rows = await task_result_dao.get_stats(
            db, name=query.name, task_id=query.task_id, start_date=start_date, end_date=end_date
        )
        status_counts: dict[str, int] = {row.status: row.count for row in status_rows}
        success_count = status_counts.get(states.SUCCESS, 0)
        failure_count = status_counts.get(states.FAILURE, 0)
        # PENDING / STARTED / RETRY 等未完成状态归入 pending
        pending_count = sum(
            count for status, count in status_counts.items() if status not in (states.SUCCESS, states.FAILURE)
        )
        total = sum(status_counts.values())
        success_rate = round(success_count / total * 100, 2) if total > 0 else 0.0

        # 2. 每日执行趋势（按日期 + 状态聚合）
        trend_rows = await task_result_dao.get_daily_trend(
            db, name=query.name, task_id=query.task_id, start_date=start_date, end_date=end_date
        )
        # 将 (date, status, count) 按日期分组汇总
        trend_map: dict[date, dict[str, int]] = defaultdict(lambda: {'success': 0, 'failure': 0, 'total': 0})
        for row in trend_rows:
            day = row.done_date
            cnt = row.count
            trend_map[day]['total'] += cnt
            if row.status == states.SUCCESS:
                trend_map[day]['success'] = cnt
            elif row.status == states.FAILURE:
                trend_map[day]['failure'] = cnt

        daily_trend = [
            TaskResultDailyTrend(
                date=day,
                success_count=vals['success'],
                failure_count=vals['failure'],
                total_count=vals['total'],
            )
            for day, vals in sorted(trend_map.items())
        ]

        # 3. 最近 N 次执行摘要
        recent_rows = await task_result_dao.get_recent_executions(
            db, name=query.name, task_id=query.task_id, limit=query.recent_limit
        )
        recent_executions = [TaskResultRecentExecution.model_validate(row) for row in recent_rows]

        return TaskResultStatsData(
            total=total,
            success_count=success_count,
            failure_count=failure_count,
            pending_count=pending_count,
            success_rate=success_rate,
            daily_trend=daily_trend,
            recent_executions=recent_executions,
        )

    @staticmethod
    async def cleanup(*, db: AsyncSession, obj: CleanupTaskResultParam) -> CleanupTaskResultResult:
        """
        按条件清理任务结果

        支持按任务名、任务 ID、执行状态、时间范围组合条件批量删除。
        至少需要提供一个过滤条件，防止误删全表数据。

        :param db: 数据库会话
        :param obj: 清理条件参数
        :return: 清理结果（删除记录数）
        """
        # 安全校验：至少需要一个过滤条件，防止空条件误删全表
        if all(v is None for v in (obj.name, obj.task_id, obj.status, obj.start_date, obj.end_date)):
            raise errors.RequestError(msg='请至少提供一个过滤条件，不能无条件清理全部数据')

        deleted_count = await task_result_dao.cleanup_by_conditions(
            db,
            name=obj.name,
            task_id=obj.task_id,
            status=obj.status,
            start_date=obj.start_date,
            end_date=obj.end_date,
        )
        return CleanupTaskResultResult(deleted_count=deleted_count)


task_result_service: TaskResultService = TaskResultService()
