from datetime import date, datetime
from typing import Any

from pydantic import ConfigDict, Field, field_serializer

from backend.app.task import celery_app
from backend.common.schema import SchemaBase


class TaskResultSchemaBase(SchemaBase):
    """任务结果基础模型"""

    task_id: str = Field(description='任务 ID')
    status: str = Field(description='执行状态')
    result: Any | None = Field(description='执行结果')
    date_done: datetime | None = Field(description='结束时间')
    traceback: str | None = Field(description='错误回溯')
    name: str | None = Field(description='任务名称')
    args: bytes | None = Field(description='任务位置参数')
    kwargs: bytes | None = Field(description='任务关键字参数')
    worker: str | None = Field(description='运行 Worker')
    retries: int | None = Field(description='重试次数')
    queue: str | None = Field(description='运行队列')


class DeleteTaskResultParam(SchemaBase):
    """删除任务结果参数"""

    pks: list[int] = Field(description='任务结果 ID 列表')


class GetTaskResultDetail(TaskResultSchemaBase):
    """任务结果详情"""

    model_config = ConfigDict(from_attributes=True)

    id: int = Field(description='任务结果 ID')

    @field_serializer('args', 'kwargs', when_used='unless-none')
    def serialize_params(self, value: bytes | None) -> Any:
        return celery_app.backend.decode(value)


class TaskResultStatsQuery(SchemaBase):
    """任务结果统计查询参数"""

    name: str | None = Field(default=None, description='任务名称（模糊匹配）')
    task_id: str | None = Field(default=None, description='任务 ID（精确匹配）')
    start_date: date | None = Field(default=None, description='统计起始日期（含），默认 7 天前')
    end_date: date | None = Field(default=None, description='统计截止日期（含），默认今天')
    recent_limit: int = Field(default=10, ge=1, le=50, description='最近执行摘要条数')


class TaskResultDailyTrend(SchemaBase):
    """任务结果每日趋势"""

    date: date = Field(description='日期')
    success_count: int = Field(description='成功次数')
    failure_count: int = Field(description='失败次数')
    total_count: int = Field(description='总次数')


class TaskResultRecentExecution(SchemaBase):
    """最近执行摘要"""

    model_config = ConfigDict(from_attributes=True)

    id: int = Field(description='任务结果 ID')
    task_id: str = Field(description='任务 ID')
    name: str | None = Field(description='任务名称')
    status: str = Field(description='执行状态')
    date_done: datetime | None = Field(description='结束时间')
    worker: str | None = Field(description='运行 Worker')
    retries: int | None = Field(description='重试次数')


class TaskResultStatsData(SchemaBase):
    """任务结果统计数据"""

    total: int = Field(description='总执行次数')
    success_count: int = Field(description='成功次数')
    failure_count: int = Field(description='失败次数')
    pending_count: int = Field(description='待处理次数（含 PENDING / STARTED / RETRY）')
    success_rate: float = Field(description='成功率（百分比，0.00 ~ 100.00）')
    daily_trend: list[TaskResultDailyTrend] = Field(description='每日执行趋势')
    recent_executions: list[TaskResultRecentExecution] = Field(description='最近执行摘要')


class CleanupTaskResultParam(SchemaBase):
    """按条件清理任务结果参数"""

    name: str | None = Field(default=None, description='任务名称（模糊匹配）')
    task_id: str | None = Field(default=None, description='任务 ID（精确匹配）')
    status: str | None = Field(default=None, description='执行状态（精确匹配，如 SUCCESS / FAILURE / PENDING）')
    start_date: date | None = Field(default=None, description='起始日期（含），按 date_done 筛选')
    end_date: date | None = Field(default=None, description='截止日期（含），按 date_done 筛选')


class CleanupTaskResultResult(SchemaBase):
    """按条件清理任务结果返回"""

    deleted_count: int = Field(description='删除的记录数')
