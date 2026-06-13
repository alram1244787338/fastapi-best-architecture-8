from typing import Any

from pydantic import BaseModel, Field


class GetPluginDetail(BaseModel):
    """插件详情"""

    name: str = Field(description='插件名称')
    summary: str = Field(description='插件摘要')
    version: str = Field(description='版本号')
    description: str = Field(description='描述')
    author: str = Field(description='作者')
    tags: list[str] = Field(default_factory=list, description='标签')
    database: list[str] = Field(default_factory=list, description='支持的数据库类型')
    depends_on: list[str] = Field(default_factory=list, description='依赖的其他插件')
    enable: str = Field(description='启用状态: 0=禁用, 1=启用')
    level: str = Field(description='插件级别: app=应用级, extend=扩展级')
    readme: str | None = Field(None, description='README.md 内容')
    is_required: bool = Field(False, description='是否为系统必需插件')
    app: dict[str, Any] | None = Field(None, description='app 配置')
    api: dict[str, Any] | None = Field(None, description='api 配置')
    settings: dict[str, Any] | None = Field(None, description='插件配置项')


class GetPluginPreCheck(BaseModel):
    """插件安装预检查结果"""

    can_install: bool = Field(description='是否可以通过安装检查')
    plugin_name: str = Field(description='解析出的插件名称')
    reason: str | None = Field(None, description='不能安装时的原因说明')
