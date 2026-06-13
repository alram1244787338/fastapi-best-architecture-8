from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query

from backend.app.task.schema.result import (
    CleanupTaskResultParam,
    CleanupTaskResultResult,
    DeleteTaskResultParam,
    GetTaskResultDetail,
    TaskResultStatsData,
)
from backend.app.task.service.result_service import task_result_service
from backend.common.pagination import DependsPagination, PageData
from backend.common.response.response_schema import ResponseModel, ResponseSchemaModel, response_base
from backend.common.security.jwt import DependsJwtAuth
from backend.common.security.permission import RequestPermission
from backend.common.security.rbac import DependsRBAC
from backend.database.db import CurrentSession, CurrentSessionTransaction

router = APIRouter()


@router.get(
    '/stats',
    summary='任务结果统计',
    dependencies=[DependsJwtAuth],
)
async def get_task_result_stats(
    db: CurrentSession,
    name: Annotated[str | None, Query(description='任务名称（模糊匹配）')] = None,
    task_id: Annotated[str | None, Query(description='任务 ID（精确匹配）')] = None,
    start_date: Annotated[date | None, Query(description='统计起始日期（含），默认最近 7 天')] = None,
    end_date: Annotated[date | None, Query(description='统计截止日期（含），默认今天')] = None,
    recent_limit: Annotated[int, Query(ge=1, le=50, description='最近执行摘要条数')] = 10,
) -> ResponseSchemaModel[TaskResultStatsData]:
    from backend.app.task.schema.result import TaskResultStatsQuery

    query = TaskResultStatsQuery(
        name=name,
        task_id=task_id,
        start_date=start_date,
        end_date=end_date,
        recent_limit=recent_limit,
    )
    data = await task_result_service.get_stats(db=db, query=query)
    return response_base.success(data=data)


@router.get('/{pk}', summary='获取任务结果详情', dependencies=[DependsJwtAuth])
async def get_task_result(
    db: CurrentSession,
    pk: Annotated[int, Path(description='任务结果 ID')],
) -> ResponseSchemaModel[GetTaskResultDetail]:
    result = await task_result_service.get(db=db, pk=pk)
    return response_base.success(data=result)


@router.get(
    '',
    summary='分页获取所有任务结果',
    dependencies=[
        DependsJwtAuth,
        DependsPagination,
    ],
)
async def get_task_results_paginated(
    db: CurrentSession,
    name: Annotated[str | None, Query(description='任务名称')] = None,
    task_id: Annotated[str | None, Query(description='任务 ID')] = None,
) -> ResponseSchemaModel[PageData[GetTaskResultDetail]]:
    page_data = await task_result_service.get_list(db=db, name=name, task_id=task_id)
    return response_base.success(data=page_data)


@router.delete(
    '',
    summary='批量删除任务结果',
    dependencies=[
        Depends(RequestPermission('sys:task:del')),
        DependsRBAC,
    ],
)
async def delete_task_result(db: CurrentSessionTransaction, obj: DeleteTaskResultParam) -> ResponseModel:
    count = await task_result_service.delete(db=db, obj=obj)
    if count > 0:
        return response_base.success()
    return response_base.fail()


@router.delete(
    '/cleanup',
    summary='按条件清理任务结果',
    dependencies=[
        Depends(RequestPermission('sys:task:del')),
        DependsRBAC,
    ],
)
async def cleanup_task_results(
    db: CurrentSessionTransaction, obj: CleanupTaskResultParam
) -> ResponseSchemaModel[CleanupTaskResultResult]:
    data = await task_result_service.cleanup(db=db, obj=obj)
    return response_base.success(data=data)
