from datetime import datetime

from pydantic import ConfigDict, Field
from pydantic.types import JsonValue

from backend.app.task.enums import PeriodType, TaskSchedulerType
from backend.common.schema import SchemaBase


class TaskSchedulerSchemeBase(SchemaBase):
    """任务调度参数"""

    name: str = Field(description='任务名称')
    task: str = Field(description='要运行的 Celery 任务')
    args: JsonValue | None = Field(default=None, description='任务可接收的位置参数')
    kwargs: JsonValue | None = Field(default=None, description='任务可接收的关键字参数')
    queue: str | None = Field(default=None, description='CELERY_TASK_QUEUES 中定义的队列')
    exchange: str | None = Field(default=None, description='低级别 AMQP 路由的交换机')
    routing_key: str | None = Field(default=None, description='低级别 AMQP 路由的路由密钥')
    start_time: datetime | None = Field(default=None, description='任务开始触发的时间')
    expire_time: datetime | None = Field(default=None, description='任务不再触发的截止时间')
    expire_seconds: int | None = Field(default=None, description='任务不再触发的秒数时间差')
    type: TaskSchedulerType = Field(description='任务调度类型（0间隔 1定时）')
    interval_every: int | None = Field(default=None, description='任务再次运行前的间隔周期数')
    interval_period: PeriodType | None = Field(default=None, description='任务运行之间的周期类型')
    crontab: str = Field(default='* * * * *', description='Crontab 表达式')
    one_off: bool = Field(default=False, description='是否仅运行一次')
    remark: str | None = Field(default=None, description='备注')


class CreateTaskSchedulerParam(TaskSchedulerSchemeBase):
    """创建任务调度参数"""


class UpdateTaskSchedulerParam(TaskSchedulerSchemeBase):
    """更新任务调度参数"""


class PreviewTaskSchedulerParam(SchemaBase):
    """任务调度预览参数"""

    type: TaskSchedulerType = Field(description='任务调度类型（0间隔 1定时）')
    crontab: str = Field(default='* * * * *', description='Crontab 表达式（type=1 时必填）')
    interval_every: int | None = Field(default=None, description='间隔周期数（type=0 时必填）')
    interval_period: PeriodType | None = Field(default=None, description='周期类型（type=0 时必填）')
    start_time: datetime | None = Field(default=None, description='预览起始时间，默认为当前时间')
    count: int = Field(default=5, ge=1, le=20, description='预览未来执行次数')


class PreviewTaskSchedulerResult(SchemaBase):
    """任务调度预览结果"""

    next_run_times: list[datetime] = Field(description='未来执行时间列表')
    timezone: str = Field(description='计算执行时间所使用的时区')
    count: int = Field(description='实际返回的执行时间数量')
    type: TaskSchedulerType = Field(description='任务调度类型')
    crontab: str | None = Field(default=None, description='Crontab 表达式')
    interval_every: int | None = Field(default=None, description='间隔周期数')
    interval_period: PeriodType | None = Field(default=None, description='周期类型')


class GetTaskSchedulerDetail(TaskSchedulerSchemeBase):
    """任务调度详情"""

    model_config = ConfigDict(from_attributes=True)

    id: int = Field(description='任务调度 ID')
    enabled: bool = Field(description='是否启用任务')
    total_run_count: int = Field(description='已运行总次数')
    last_run_time: datetime | None = Field(None, description='最后运行时间')
    created_time: datetime = Field(description='创建时间')
    updated_time: datetime | None = Field(None, description='更新时间')
