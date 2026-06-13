import io
import json

from typing import Any

import anyio

from fastapi import UploadFile
from starlette.concurrency import run_in_threadpool

from backend.app.admin.schema.plugin import GetPluginDetail
from backend.common.enums import PluginLevelType, PluginType, StatusType
from backend.common.exception import errors
from backend.core.conf import settings
from backend.core.path_conf import PLUGIN_DIR
from backend.database.redis import redis_client
from backend.plugin.core import (
    check_plugin_installed,
    get_plugin_readme,
    get_required_plugins,
    load_plugin_config,
)
from backend.plugin.installer import (
    install_git_plugin,
    install_zip_plugin,
    remove_plugin,
    validate_git_repo_url,
    validate_zip_plugin_contents,
    zip_plugin,
)
from backend.plugin.requirements import uninstall_requirements_async
from backend.utils.timezone import timezone


class PluginService:
    """插件服务类"""

    @staticmethod
    async def get_all() -> list[dict[str, Any]]:
        """获取所有插件"""

        changed_key = f'{settings.PLUGIN_REDIS_PREFIX}:changed'
        keys = [key for key in await redis_client.get_prefix(f'{settings.PLUGIN_REDIS_PREFIX}:') if key != changed_key]
        if not keys:
            return []

        result = []
        required_plugins = get_required_plugins()
        plugin_infos = await redis_client.mget(*keys)
        for info in plugin_infos:
            if info is None:
                continue

            plugin_info = json.loads(info)
            if isinstance(plugin_info, dict):
                # 补充列表页常用的派生字段，避免前端再次请求详情即可完成基础展示
                plugin_name = plugin_info.get('plugin', {}).get('name', '')
                if plugin_name:
                    plugin_info['plugin']['is_required'] = plugin_name in required_plugins
                    plugin_info['plugin']['has_readme'] = (PLUGIN_DIR / plugin_name / 'README.md').exists()
                plugin_info.setdefault(
                    'level',
                    PluginLevelType.extend.value if 'api' in plugin_info else PluginLevelType.app.value,
                )
                result.append(plugin_info)

        return result

    @staticmethod
    async def changed() -> str | None:
        """检查插件是否发生变更"""
        return await redis_client.get(f'{settings.PLUGIN_REDIS_PREFIX}:changed')

    @staticmethod
    async def get_detail(*, plugin: str) -> GetPluginDetail:
        """
        获取插件详情

        优先读取服务启动时注入的 Redis 缓存；缓存未命中时回退读取磁盘上的 plugin.toml，
        方便管理员在插件安装后、服务重启前也能查看插件信息。

        :param plugin: 插件名称
        :return:
        """
        cached = await redis_client.get(f'{settings.PLUGIN_REDIS_PREFIX}:{plugin}')
        if cached:
            config: dict[str, Any] = json.loads(cached)
        elif check_plugin_installed(plugin):
            try:
                config = await run_in_threadpool(load_plugin_config, plugin)
            except Exception as e:
                reason = getattr(e, 'msg', str(e))
                raise errors.ServerError(msg=f'插件 {plugin} 配置读取失败: {reason}') from e
            config.setdefault('plugin', {})
            config['plugin'].setdefault('name', plugin)
            config['plugin'].setdefault('enable', str(StatusType.enable.value))
        else:
            raise errors.NotFoundError(msg='插件不存在')

        meta: dict[str, Any] = config.get('plugin', {})
        depends_on = meta.get('depends_on') or []
        readme = await run_in_threadpool(get_plugin_readme, plugin)

        return GetPluginDetail(
            name=meta.get('name', plugin),
            summary=meta.get('summary', ''),
            version=meta.get('version', ''),
            description=meta.get('description', ''),
            author=meta.get('author', ''),
            tags=meta.get('tags') or [],
            database=meta.get('database') or [],
            depends_on=depends_on,
            enable=str(meta.get('enable', StatusType.enable.value)),
            level=PluginLevelType.extend.value if 'api' in config else PluginLevelType.app.value,
            readme=readme,
            is_required=plugin in get_required_plugins(),
            installed=check_plugin_installed(plugin),
            missing_depends=[dep for dep in depends_on if not check_plugin_installed(dep)],
            app=config.get('app'),
            api=config.get('api'),
            settings=config.get('settings'),
        )

    @staticmethod
    async def pre_check_install(
        *,
        type: PluginType,
        file: UploadFile | None = None,
        repo_url: str | None = None,
    ) -> str:
        """
        安装前预检查

        在不写入任何文件的前提下校验参数完整性、ZIP 压缩包结构或 Git 仓库地址的合法性，
        并提前发现“插件已安装”等问题，返回解析出的插件名称。

        :param type: 插件类型
        :param file: 插件 zip 压缩包
        :param repo_url: 插件 git 仓库地址
        :return:
        """
        if settings.ENVIRONMENT != 'dev':
            raise errors.RequestError(msg='禁止在非开发环境下安装插件')

        if type == PluginType.zip:
            if not file:
                raise errors.RequestError(msg='ZIP 压缩包不能为空')
            contents = await file.read()
            if not contents:
                raise errors.RequestError(msg='ZIP 压缩包内容为空')
            plugin_name, _ = validate_zip_plugin_contents(contents, file.filename or '')
        else:
            if not repo_url:
                raise errors.RequestError(msg='Git 仓库地址不能为空')
            plugin_name = validate_git_repo_url(repo_url)

        if await anyio.Path(PLUGIN_DIR / plugin_name).exists():
            raise errors.ConflictError(msg=f'插件 {plugin_name} 已安装，如需重新安装请先卸载')

        return plugin_name

    @staticmethod
    async def install(*, type: PluginType, file: UploadFile | None = None, repo_url: str | None = None) -> str:
        """
        安装插件

        :param type: 插件类型
        :param file: 插件 zip 压缩包
        :param repo_url: git 仓库地址
        :return:
        """
        if settings.ENVIRONMENT != 'dev':
            raise errors.RequestError(msg='禁止在非开发环境下安装插件')

        # 安装前先做预检查，提前暴露常见问题（参数缺失、压缩包结构、仓库地址、已安装等）
        await PluginService.pre_check_install(type=type, file=file, repo_url=repo_url)

        # 预检查已读取过上传文件，需重置读取位置供 installer 再次读取
        if file is not None:
            await file.seek(0)

        if type == PluginType.zip:
            return await install_zip_plugin(file)
        return await install_git_plugin(repo_url)

    @staticmethod
    async def uninstall(*, plugin: str) -> None:
        """
        卸载插件

        :param plugin: 插件名称
        :return:
        """
        if settings.ENVIRONMENT != 'dev':
            raise errors.RequestError(msg='禁止在非开发环境下卸载插件')
        if plugin in get_required_plugins():
            raise errors.RequestError(msg=f'插件 {plugin} 为必需插件，禁止卸载')
        plugin_dir = anyio.Path(PLUGIN_DIR / plugin)
        if not await plugin_dir.exists():
            raise errors.NotFoundError(msg='插件不存在')
        await uninstall_requirements_async(plugin)
        backup_file = PLUGIN_DIR / f'{plugin}.{timezone.now().strftime("%Y%m%d%H%M%S")}.backup.zip'
        await run_in_threadpool(zip_plugin, plugin_dir, backup_file)
        await run_in_threadpool(remove_plugin, plugin_dir)
        await redis_client.delete(f'{settings.PLUGIN_REDIS_PREFIX}:{plugin}')
        await redis_client.set(f'{settings.PLUGIN_REDIS_PREFIX}:changed', 'true')

    @staticmethod
    async def update_status(*, plugin: str) -> None:
        """
        更新插件状态

        :param plugin: 插件名称
        :return:
        """
        plugin_key = f'{settings.PLUGIN_REDIS_PREFIX}:{plugin}'
        plugin_info = await redis_client.get(plugin_key)
        if not plugin_info:
            raise errors.NotFoundError(msg='插件不存在')
        plugin_info = json.loads(plugin_info)

        # 更新持久缓存状态
        new_status = (
            str(StatusType.enable.value)
            if plugin_info['plugin']['enable'] == str(StatusType.disable.value)
            else str(StatusType.disable.value)
        )
        plugin_info['plugin']['enable'] = new_status
        await redis_client.set(plugin_key, json.dumps(plugin_info, ensure_ascii=False))
        await redis_client.set(f'{settings.PLUGIN_REDIS_PREFIX}:changed', 'true')

    @staticmethod
    async def build(*, plugin: str) -> io.BytesIO:
        """
        打包插件为 zip 压缩包

        :param plugin: 插件名称
        :return:
        """
        plugin_dir = anyio.Path(PLUGIN_DIR / plugin)
        if not await plugin_dir.exists():
            raise errors.NotFoundError(msg='插件不存在')

        bio = io.BytesIO()
        await run_in_threadpool(zip_plugin, plugin_dir, bio)
        bio.seek(0)
        return bio


plugin_service: PluginService = PluginService()
