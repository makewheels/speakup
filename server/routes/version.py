import os

from fastapi import APIRouter

router = APIRouter(prefix="/api", tags=["version"])


def get_version() -> str:
    """应用版本号：优先读 APP_VERSION 配置（部署/CI 注入），读不到返回 dev。"""
    return os.getenv("APP_VERSION") or "dev"


@router.get("/version")
async def version():
    """只读版本/健康探针：返回版本号与状态，不依赖数据库或任何外部服务。"""
    return {"version": get_version(), "status": "ok"}
