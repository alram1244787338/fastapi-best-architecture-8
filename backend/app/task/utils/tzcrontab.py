from datetime import datetime, timedelta

from celery import schedules
from celery.schedules import ParseException

from backend.common.exception import errors
from backend.utils.timezone import timezone


class TzAwareCrontab(schedules.crontab):
    """时区感知 Crontab"""

    def __init__(self, minute='*', hour='*', day_of_week='*', day_of_month='*', month_of_year='*', app=None) -> None:  # noqa: ANN001
        super().__init__(
            minute=minute,
            hour=hour,
            day_of_week=day_of_week,
            day_of_month=day_of_month,
            month_of_year=month_of_year,
            nowfun=timezone.now,
            app=app,
        )


def crontab_verify(crontab: str) -> None:
    """
    验证标准 crontab 表达式

    :param crontab: 标准 crontab 表达式
    :return:
    """
    crontab_split = crontab.split(' ')
    if len(crontab_split) != 5:
        raise errors.RequestError(msg='Crontab 表达式非法')
    try:
        TzAwareCrontab.from_string(crontab)
    except (ParseException, ValueError):
        raise errors.RequestError(msg='Crontab 表达式非法')


def _localize(dt: datetime) -> datetime:
    """
    将 datetime 规范化为当前配置时区

    :param dt: 需要规范化的 datetime 对象
    :return:
    """
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.tz_info)
    return dt.astimezone(timezone.tz_info)


def crontab_next_run_times(crontab: str, count: int = 5, *, start_time: datetime | None = None) -> list[datetime]:
    """
    计算 crontab 表达式未来的执行时间

    :param crontab: 标准 crontab 表达式
    :param count: 需要预览的执行次数
    :param start_time: 预览的起始时间，默认为当前时间
    :return:
    """
    crontab_verify(crontab)

    schedule = TzAwareCrontab.from_string(crontab)

    # 以起始时间作为预览锚点，未提供时使用当前时间
    last_run_at = _localize(start_time) if start_time is not None else timezone.now()

    run_times: list[datetime] = []
    for _ in range(count):
        try:
            # remaining_delta 返回 (本地化的上次运行时间, 距离下次运行的时间差, 本地化的当前时间)
            local_last_run_at, delta, _ = schedule.remaining_delta(last_run_at)
            next_run_time = local_last_run_at + delta
        except (RuntimeError, ValueError, OverflowError):
            # 例如 0 0 31 2 * 这种永远不会命中的表达式
            raise errors.RequestError(msg='Crontab 表达式无法计算出有效的执行时间')
        next_run_time = _localize(next_run_time)
        run_times.append(next_run_time)
        last_run_at = next_run_time

    return run_times


def interval_next_run_times(
    every: int | None,
    period: str | None,
    count: int = 5,
    *,
    start_time: datetime | None = None,
) -> list[datetime]:
    """
    计算间隔型任务未来的执行时间

    :param every: 任务再次运行前的间隔周期数
    :param period: 任务运行之间的周期类型（days/hours/minutes/seconds/microseconds）
    :param count: 需要预览的执行次数
    :param start_time: 预览的起始时间，默认为当前时间
    :return:
    """
    if every is None or every <= 0:
        raise errors.RequestError(msg='间隔周期数必须为大于 0 的整数')
    if not period:
        raise errors.RequestError(msg='请选择间隔周期类型')

    try:
        interval = timedelta(**{period: every})
    except TypeError:
        raise errors.RequestError(msg='间隔周期类型非法')

    # 以起始时间作为预览锚点，未提供时使用当前时间；首次执行在一个周期之后
    base_time = _localize(start_time) if start_time is not None else timezone.now()

    run_times: list[datetime] = []
    next_run_time = base_time + interval
    for _ in range(count):
        run_times.append(next_run_time)
        next_run_time = next_run_time + interval

    return run_times
