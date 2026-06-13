import json

from collections.abc import Sequence
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from backend.app.task.celery import celery_app
from backend.app.task.crud.crud_scheduler import task_scheduler_dao
from backend.app.task.enums import PeriodType, TaskSchedulerType
from backend.app.task.model import TaskScheduler
from backend.app.task.schema.scheduler import (
    CreateTaskSchedulerParam,
    PreviewTaskSchedulerParam,
    PreviewTaskSchedulerResult,
    UpdateTaskSchedulerParam,
)
from backend.app.task.utils.tzcrontab import TzAwareCrontab, crontab_verify
from backend.common.exception import errors
from backend.common.pagination import paging_data
from backend.utils.timezone import timezone


class TaskSchedulerService:
    """任务调度服务类"""

    @staticmethod
    async def get(*, db: AsyncSession, pk: int) -> TaskScheduler | None:
        """
        获取任务调度详情

        :param db: 数据库会话
        :param pk: 任务调度 ID
        :return:
        """

        task_scheduler = await task_scheduler_dao.get(db, pk)
        if not task_scheduler:
            raise errors.NotFoundError(msg='任务调度不存在')
        return task_scheduler

    @staticmethod
    async def get_all(*, db: AsyncSession) -> Sequence[TaskScheduler]:
        """
        获取所有任务调度

        :param db: 数据库会话
        :return:
        """

        task_schedulers = await task_scheduler_dao.get_all(db)
        return task_schedulers

    @staticmethod
    async def get_list(*, db: AsyncSession, name: str | None, type: int | None) -> dict[str, Any]:
        """
        获取任务调度列表

        :param db: 数据库会话
        :param name: 任务调度名称
        :param type: 任务调度类型
        :return:
        """
        task_scheduler_select = await task_scheduler_dao.get_select(name=name, type=type)
        return await paging_data(db, task_scheduler_select)

    @staticmethod
    async def create(*, db: AsyncSession, obj: CreateTaskSchedulerParam) -> None:
        """
        创建任务调度

        :param db: 数据库会话
        :param obj: 任务调度创建参数
        :return:
        """

        task_scheduler = await task_scheduler_dao.get_by_name(db, obj.name)
        if task_scheduler:
            raise errors.ConflictError(msg='任务调度已存在')
        if obj.type == TaskSchedulerType.CRONTAB:
            crontab_verify(obj.crontab)
        await task_scheduler_dao.create(db, obj)

    @staticmethod
    async def update(*, db: AsyncSession, pk: int, obj: UpdateTaskSchedulerParam) -> int:
        """
        更新任务调度

        :param db: 数据库会话
        :param pk: 任务调度 ID
        :param obj: 任务调度更新参数
        :return:
        """

        task_scheduler = await task_scheduler_dao.get(db, pk)
        if not task_scheduler:
            raise errors.NotFoundError(msg='任务调度不存在')
        if task_scheduler.name != obj.name and await task_scheduler_dao.get_by_name(db, obj.name):
            raise errors.ConflictError(msg='任务调度已存在')
        if obj.type == TaskSchedulerType.CRONTAB:
            crontab_verify(obj.crontab)
        count = await task_scheduler_dao.update(db, pk, obj)
        return count

    @staticmethod
    async def update_status(*, db: AsyncSession, pk: int) -> int:
        """
        更新任务调度状态

        :param db: 数据库会话
        :param pk: 任务调度 ID
        :return:
        """

        task_scheduler = await task_scheduler_dao.get(db, pk)
        if not task_scheduler:
            raise errors.NotFoundError(msg='任务调度不存在')
        count = await task_scheduler_dao.set_status(db, pk, status=not task_scheduler.enabled)
        return count

    @staticmethod
    async def delete(*, db: AsyncSession, pk: int) -> int:
        """
        删除任务调度

        :param db: 数据库会话
        :param pk: 用户 ID
        :return:
        """

        task_scheduler = await task_scheduler_dao.get(db, pk)
        if not task_scheduler:
            raise errors.NotFoundError(msg='任务调度不存在')
        count = await task_scheduler_dao.delete(db, pk)
        return count

    @staticmethod
    async def execute(*, db: AsyncSession, pk: int) -> None:
        """
        执行任务

        :param db: 数据库会话
        :param pk: 任务调度 ID
        :return:
        """

        workers = await run_in_threadpool(celery_app.control.ping, timeout=0.5)
        if not workers:
            raise errors.ServerError(msg='Celery Worker 暂不可用，请稍后重试')
        task_scheduler = await task_scheduler_dao.get(db, pk)
        if not task_scheduler:
            raise errors.NotFoundError(msg='任务调度不存在')
        try:
            args = json.loads(task_scheduler.args) if task_scheduler.args else None
            kwargs = json.loads(task_scheduler.kwargs) if task_scheduler.kwargs else None
        except (TypeError, json.JSONDecodeError):
            raise errors.RequestError(msg='执行失败，任务参数非法')
        else:
            celery_app.send_task(name=task_scheduler.task, args=args, kwargs=kwargs)

    @staticmethod
    def preview(*, obj: PreviewTaskSchedulerParam) -> PreviewTaskSchedulerResult:
        """
        预览任务调度未来执行时间

        :param obj: 任务调度预览参数
        :return: 预览结果
        """
        if obj.type == TaskSchedulerType.CRONTAB:
            next_run_times = TaskSchedulerService._preview_crontab(
                crontab=obj.crontab, start_time=obj.start_time, count=obj.count
            )
            return PreviewTaskSchedulerResult(
                next_run_times=next_run_times,
                count=len(next_run_times),
                type=obj.type,
                crontab=obj.crontab,
            )
        elif obj.type == TaskSchedulerType.INTERVAL:
            next_run_times = TaskSchedulerService._preview_interval(
                interval_every=obj.interval_every,
                interval_period=obj.interval_period,
                start_time=obj.start_time,
                count=obj.count,
            )
            return PreviewTaskSchedulerResult(
                next_run_times=next_run_times,
                count=len(next_run_times),
                type=obj.type,
                interval_every=obj.interval_every,
                interval_period=obj.interval_period,
            )
        else:
            raise errors.RequestError(msg='不支持的任务调度类型')

    @staticmethod
    def _preview_crontab(*, crontab: str, start_time: datetime | None, count: int) -> list[datetime]:
        """
        预览 crontab 类型任务的未来执行时间

        :param crontab: crontab 表达式
        :param start_time: 起始时间
        :param count: 预览次数
        :return: 未来执行时间列表
        """
        crontab_verify(crontab)
        try:
            schedule = TzAwareCrontab.from_string(crontab)
        except Exception as e:
            raise errors.RequestError(msg=f'Crontab 表达式解析失败：{e}')

        base_time = start_time if start_time else timezone.now()
        if base_time.tzinfo is None:
            base_time = base_time.replace(tzinfo=timezone.tz_info)
        else:
            base_time = base_time.astimezone(timezone.tz_info)

        next_run_times = []
        current_time = base_time
        # 限制最大迭代次数，防止死循环
        max_iterations = count * 60 * 24 * 365  # 最多扫描 1 年
        iterations = 0
        while len(next_run_times) < count and iterations < max_iterations:
            is_due, next_seconds = schedule.is_due(current_time)
            if next_seconds is None or next_seconds <= 0:
                next_seconds = 60
            next_time = current_time + timedelta(seconds=float(next_seconds))
            # 确保时间在前进
            if next_time <= current_time:
                next_time = current_time + timedelta(seconds=60)
            next_run_times.append(next_time)
            current_time = next_time
            iterations += 1

        return next_run_times

    @staticmethod
    def _preview_interval(
        *,
        interval_every: int | None,
        interval_period: PeriodType | None,
        start_time: datetime | None,
        count: int,
    ) -> list[datetime]:
        """
        预览间隔类型任务的未来执行时间

        :param interval_every: 间隔周期数
        :param interval_period: 周期类型
        :param start_time: 起始时间
        :param count: 预览次数
        :return: 未来执行时间列表
        """
        if interval_every is None or interval_every <= 0:
            raise errors.RequestError(msg='间隔周期数必须大于 0')
        if interval_period is None:
            raise errors.RequestError(msg='周期类型不能为空')

        try:
            delta = timedelta(**{interval_period: interval_every})
        except (TypeError, ValueError) as e:
            raise errors.RequestError(msg=f'间隔参数非法：{e}')

        base_time = start_time if start_time else timezone.now()
        if base_time.tzinfo is None:
            base_time = base_time.replace(tzinfo=timezone.tz_info)
        else:
            base_time = base_time.astimezone(timezone.tz_info)

        next_run_times = []
        current_time = base_time
        for _ in range(count):
            current_time = current_time + delta
            next_run_times.append(current_time)

        return next_run_times


task_scheduler_service: TaskSchedulerService = TaskSchedulerService()
