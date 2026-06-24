#!/bin/bash
# --------------------------------------------------
# JCGKZX AutoTask 镜像构建与打包导出脚本
# --------------------------------------------------

# 终止后续执行如果遇到错误
set -e

# 定义镜像名称
export IMAGE_NAME="jcgkzx-autotask:latest"

# 自动检测是否需要使用 sudo 执行 docker 命令
if docker ps >/dev/null 2>&1; then
    DOCKER_CMD="docker"
    DOCKER_COMPOSE_CMD="docker compose"
    echo "检测到当前用户具有 Docker 执行权限，将直接运行命令。"
else
    DOCKER_CMD="sudo docker"
    DOCKER_COMPOSE_CMD="sudo docker compose"
    echo "检测到当前用户需要提升权限，将使用 sudo 运行命令（如果提示，请输入您的 sudo 密码）。"
fi

echo "==========================================="
echo " 步骤 1: 构建 Docker 镜像 (优先使用国内清华源)"
echo "==========================================="

# 第一阶段：尝试使用默认国内源构建
if $DOCKER_COMPOSE_CMD build; then
    echo ">>> 使用国内镜像源构建成功！"
else
    echo ">>> [警告] 国内镜像源构建失败，可能网络受限。正在自动切换至官方源进行构建..."
    
    # 第二阶段：使用官方源构建
    $DOCKER_COMPOSE_CMD build \
      --build-arg UV_INDEX_URL=https://pypi.org/simple \
      --build-arg UV_EXTRA_INDEX_URL=https://pypi.org/simple \
      --build-arg APT_MIRROR=http://deb.debian.org/debian \
      --build-arg APT_SECURITY_MIRROR=http://security.debian.org/debian-security
      
    echo ">>> 使用官方镜像源构建成功！"
fi

echo "==========================================="
echo " 步骤 2: 导出镜像为 tar 存档包到当前目录"
echo "==========================================="

TAR_PATH="./jcgkzx-autotask_latest.tar"

# 如果已有旧的包，先清理
if [ -f "$TAR_PATH" ]; then
    echo "清理已存在的旧镜像包..."
    rm -f "$TAR_PATH"
fi

# 导出镜像
$DOCKER_CMD save -o "$TAR_PATH" "$IMAGE_NAME"

# 修改属主为当前非 root 用户，避免导出文件权限为 root 导致移动不便
if [[ "$DOCKER_CMD" == *"sudo"* ]]; then
    CURRENT_USER=$(whoami)
    sudo chown "$CURRENT_USER:$CURRENT_USER" "$TAR_PATH"
fi

echo "==========================================="
echo " 构建与导出完成！"
echo " 镜像存档包已输出至: $(pwd)/jcgkzx-autotask_latest.tar"
echo "==========================================="
