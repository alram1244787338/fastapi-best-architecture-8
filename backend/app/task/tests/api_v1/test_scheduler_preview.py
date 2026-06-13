"""任务调度预览功能测试"""

from datetime import datetime

import pytest

from backend.app.task.enums import PeriodType, TaskSchedulerType
from backend.app.task.schema.scheduler import PreviewTaskSchedulerParam
from backend.app.task.service.scheduler_service import TaskSchedulerService
from backend.common.exception.errors import RequestError
from backend.core.conf import settings
from backend.utils.timezone import timezone


class TestPreviewCrontab:
    """Crontab 类型预览测试"""

    def test_preview_every_minute(self) -> None:
        """测试每分钟执行"""
        obj = PreviewTaskSchedulerParam(
            type=TaskSchedulerType.CRONTAB,
            crontab='* * * * *',
            count=5,
        )
        result = TaskSchedulerService.preview(obj=obj)
        assert result.count == 5
        assert len(result.next_run_times) == 5
        assert result.type == TaskSchedulerType.CRONTAB
        assert result.crontab == '* * * * *'
        # 验证时间递增
        for i in range(1, len(result.next_run_times)):
            assert result.next_run_times[i] > result.next_run_times[i - 1]

    def test_preview_hourly(self) -> None:
        """测试每小时执行"""
        obj = PreviewTaskSchedulerParam(
            type=TaskSchedulerType.CRONTAB,
            crontab='0 * * * *',
            count=3,
        )
        result = TaskSchedulerService.preview(obj=obj)
        assert result.count == 3
        # 验证每次执行间隔约 1 小时
        for i in range(1, len(result.next_run_times)):
            delta = result.next_run_times[i] - result.next_run_times[i - 1]
            assert delta.total_seconds() >= 3600 - 1  # 允许 1 秒误差

    def test_preview_daily_at_midnight(self) -> None:
        """测试每天午夜执行"""
        obj = PreviewTaskSchedulerParam(
            type=TaskSchedulerType.CRONTAB,
            crontab='0 0 * * *',
            count=3,
        )
        result = TaskSchedulerService.preview(obj=obj)
        assert result.count == 3
        # 验证每次执行间隔约 24 小时
        for i in range(1, len(result.next_run_times)):
            delta = result.next_run_times[i] - result.next_run_times[i - 1]
            assert delta.total_seconds() >= 86400 - 60  # 允许 1 分钟误差

    def test_preview_specific_time(self) -> None:
        """测试特定时间执行（每天 9:30）"""
        obj = PreviewTaskSchedulerParam(
            type=TaskSchedulerType.CRONTAB,
            crontab='30 9 * * *',
            count=2,
        )
        result = TaskSchedulerService.preview(obj=obj)
        assert result.count == 2
        for run_time in result.next_run_times:
            assert run_time.hour == 9
            assert run_time.minute == 30

    def test_preview_with_start_time(self) -> None:
        """测试指定起始时间"""
        start = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.tz_info)
        obj = PreviewTaskSchedulerParam(
            type=TaskSchedulerType.CRONTAB,
            crontab='0 12 * * *',
            start_time=start,
            count=2,
        )
        result = TaskSchedulerService.preview(obj=obj)
        assert result.count == 2
        # 第一次执行应在 2026-01-01 12:00 或之后
        assert result.next_run_times[0] >= start

    def test_preview_invalid_crontab(self) -> None:
        """测试非法 crontab 表达式"""
        obj = PreviewTaskSchedulerParam(
            type=TaskSchedulerType.CRONTAB,
            crontab='invalid cron',
            count=5,
        )
        with pytest.raises(RequestError) as exc_info:
            TaskSchedulerService.preview(obj=obj)
        assert 'Crontab' in str(exc_info.value.msg)

    def test_preview_empty_crontab(self) -> None:
        """测试空 crontab 表达式"""
        obj = PreviewTaskSchedulerParam(
            type=TaskSchedulerType.CRONTAB,
            crontab='',
            count=5,
        )
        with pytest.raises(RequestError):
            TaskSchedulerService.preview(obj=obj)

    def test_preview_too_many_fields(self) -> None:
        """测试字段过多的 crontab 表达式"""
        obj = PreviewTaskSchedulerParam(
            type=TaskSchedulerType.CRONTAB,
            crontab='* * * * * *',
            count=5,
        )
        with pytest.raises(RequestError):
            TaskSchedulerService.preview(obj=obj)

    def test_preview_impossible_crontab(self) -> None:
        """测试永远不会命中的 crontab 表达式（2 月 31 日）"""
        obj = PreviewTaskSchedulerParam(
            type=TaskSchedulerType.CRONTAB,
            crontab='0 0 31 2 *',
            count=3,
        )
        with pytest.raises(RequestError) as exc_info:
            TaskSchedulerService.preview(obj=obj)
        assert 'Crontab' in str(exc_info.value.msg)


class TestPreviewInterval:
    """间隔类型预览测试"""

    def test_preview_every_30_minutes(self) -> None:
        """测试每 30 分钟执行"""
        obj = PreviewTaskSchedulerParam(
            type=TaskSchedulerType.INTERVAL,
            interval_every=30,
            interval_period=PeriodType.MINUTES,
            count=5,
        )
        result = TaskSchedulerService.preview(obj=obj)
        assert result.count == 5
        assert result.type == TaskSchedulerType.INTERVAL
        assert result.interval_every == 30
        assert result.interval_period == PeriodType.MINUTES
        # 验证每次执行间隔 30 分钟
        for i in range(1, len(result.next_run_times)):
            delta = result.next_run_times[i] - result.next_run_times[i - 1]
            assert delta.total_seconds() == 1800

    def test_preview_every_2_hours(self) -> None:
        """测试每 2 小时执行"""
        obj = PreviewTaskSchedulerParam(
            type=TaskSchedulerType.INTERVAL,
            interval_every=2,
            interval_period=PeriodType.HOURS,
            count=3,
        )
        result = TaskSchedulerService.preview(obj=obj)
        assert result.count == 3
        for i in range(1, len(result.next_run_times)):
            delta = result.next_run_times[i] - result.next_run_times[i - 1]
            assert delta.total_seconds() == 7200

    def test_preview_every_day(self) -> None:
        """测试每天执行"""
        obj = PreviewTaskSchedulerParam(
            type=TaskSchedulerType.INTERVAL,
            interval_every=1,
            interval_period=PeriodType.DAYS,
            count=3,
        )
        result = TaskSchedulerService.preview(obj=obj)
        assert result.count == 3
        for i in range(1, len(result.next_run_times)):
            delta = result.next_run_times[i] - result.next_run_times[i - 1]
            assert delta.total_seconds() == 86400

    def test_preview_every_10_seconds(self) -> None:
        """测试每 10 秒执行"""
        obj = PreviewTaskSchedulerParam(
            type=TaskSchedulerType.INTERVAL,
            interval_every=10,
            interval_period=PeriodType.SECONDS,
            count=5,
        )
        result = TaskSchedulerService.preview(obj=obj)
        assert result.count == 5
        for i in range(1, len(result.next_run_times)):
            delta = result.next_run_times[i] - result.next_run_times[i - 1]
            assert delta.total_seconds() == 10

    def test_preview_with_start_time(self) -> None:
        """测试指定起始时间"""
        start = datetime(2026, 6, 1, 10, 0, 0, tzinfo=timezone.tz_info)
        obj = PreviewTaskSchedulerParam(
            type=TaskSchedulerType.INTERVAL,
            interval_every=1,
            interval_period=PeriodType.HOURS,
            start_time=start,
            count=3,
        )
        result = TaskSchedulerService.preview(obj=obj)
        assert result.count == 3
        # 第一次执行应在 2026-06-01 11:00:00
        assert result.next_run_times[0] == datetime(2026, 6, 1, 11, 0, 0, tzinfo=timezone.tz_info)

    def test_preview_missing_interval_every(self) -> None:
        """测试缺少间隔周期数"""
        obj = PreviewTaskSchedulerParam(
            type=TaskSchedulerType.INTERVAL,
            interval_period=PeriodType.HOURS,
            count=5,
        )
        with pytest.raises(RequestError) as exc_info:
            TaskSchedulerService.preview(obj=obj)
        assert '间隔周期数' in str(exc_info.value.msg)

    def test_preview_missing_interval_period(self) -> None:
        """测试缺少周期类型"""
        obj = PreviewTaskSchedulerParam(
            type=TaskSchedulerType.INTERVAL,
            interval_every=1,
            count=5,
        )
        with pytest.raises(RequestError) as exc_info:
            TaskSchedulerService.preview(obj=obj)
        assert '周期类型' in str(exc_info.value.msg)

    def test_preview_zero_interval(self) -> None:
        """测试间隔为 0"""
        obj = PreviewTaskSchedulerParam(
            type=TaskSchedulerType.INTERVAL,
            interval_every=0,
            interval_period=PeriodType.HOURS,
            count=5,
        )
        with pytest.raises(RequestError) as exc_info:
            TaskSchedulerService.preview(obj=obj)
        assert '大于 0' in str(exc_info.value.msg)

    def test_preview_negative_interval(self) -> None:
        """测试负数间隔"""
        obj = PreviewTaskSchedulerParam(
            type=TaskSchedulerType.INTERVAL,
            interval_every=-1,
            interval_period=PeriodType.HOURS,
            count=5,
        )
        with pytest.raises(RequestError):
            TaskSchedulerService.preview(obj=obj)


class TestPreviewSchemaValidation:
    """预览参数校验测试"""

    def test_count_too_large(self) -> None:
        """测试预览次数超出上限"""
        with pytest.raises(Exception):
            PreviewTaskSchedulerParam(
                type=TaskSchedulerType.CRONTAB,
                crontab='* * * * *',
                count=100,
            )

    def test_count_too_small(self) -> None:
        """测试预览次数小于下限"""
        with pytest.raises(Exception):
            PreviewTaskSchedulerParam(
                type=TaskSchedulerType.CRONTAB,
                crontab='* * * * *',
                count=0,
            )

    def test_count_within_range(self) -> None:
        """测试预览次数在有效范围内"""
        obj = PreviewTaskSchedulerParam(
            type=TaskSchedulerType.CRONTAB,
            crontab='* * * * *',
            count=10,
        )
        assert obj.count == 10

    def test_default_count(self) -> None:
        """测试默认预览次数"""
        obj = PreviewTaskSchedulerParam(
            type=TaskSchedulerType.CRONTAB,
            crontab='* * * * *',
        )
        assert obj.count == 5


class TestPreviewTimezone:
    """预览结果时区测试"""

    def test_crontab_result_timezone(self) -> None:
        """测试 crontab 预览结果携带配置时区且执行时间为时区感知"""
        obj = PreviewTaskSchedulerParam(
            type=TaskSchedulerType.CRONTAB,
            crontab='0 9 * * *',
            count=3,
        )
        result = TaskSchedulerService.preview(obj=obj)
        assert result.timezone == settings.DATETIME_TIMEZONE
        for run_time in result.next_run_times:
            assert run_time.tzinfo is not None

    def test_interval_result_timezone(self) -> None:
        """测试间隔预览结果携带配置时区且执行时间为时区感知"""
        obj = PreviewTaskSchedulerParam(
            type=TaskSchedulerType.INTERVAL,
            interval_every=15,
            interval_period=PeriodType.MINUTES,
            count=3,
        )
        result = TaskSchedulerService.preview(obj=obj)
        assert result.timezone == settings.DATETIME_TIMEZONE
        for run_time in result.next_run_times:
            assert run_time.tzinfo is not None
