#!/bin/bash

echo "========================================"
echo "  读书解构大师 - 快速启动脚本"
echo "========================================"
echo ""

# 检查 .env 文件
if [ ! -f .env ]; then
    echo "[错误] 未找到 .env 文件！"
    echo ""
    echo "请先创建 .env 文件，内容如下："
    echo "DEEPSEEK_API_KEY=sk-你的API密钥"
    echo "OUTPUT_DIRECTORY=./output"
    echo ""
    exit 1
fi

# 检查 Docker
echo "[1/3] 检查 Docker 是否安装..."
if ! command -v docker &> /dev/null; then
    echo "[错误] 未检测到 Docker，请先安装 Docker"
    exit 1
fi
echo "[✓] Docker 已安装"

# 启动服务
echo ""
echo "[2/3] 启动 Docker 服务..."
docker-compose up -d --build

if [ $? -ne 0 ]; then
    echo "[错误] 启动失败，请检查错误信息"
    exit 1
fi

echo ""
echo "[3/3] 等待服务启动..."
sleep 3

echo ""
echo "========================================"
echo "  ✓ 启动成功！"
echo "========================================"
echo ""
echo "  请在浏览器中访问: http://localhost:8000"
echo ""
echo "提示：要停止服务，请运行: docker-compose down"
echo ""

# 尝试打开浏览器（Linux/Mac）
if command -v xdg-open &> /dev/null; then
    xdg-open http://localhost:8000 2>/dev/null
elif command -v open &> /dev/null; then
    open http://localhost:8000 2>/dev/null
fi
