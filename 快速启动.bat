@echo off
chcp 65001 >nul
echo ========================================
echo   读书解构大师 - 快速启动脚本
echo ========================================
echo.

REM 检查 .env 文件是否存在
if not exist .env (
    echo [错误] 未找到 .env 文件！
    echo.
    echo 请先创建 .env 文件，内容如下：
    echo DEEPSEEK_API_KEY=sk-你的API密钥
    echo OUTPUT_DIRECTORY=./output
    echo.
    pause
    exit /b 1
)

echo [1/3] 检查 Docker 是否安装...
docker --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未检测到 Docker，请先安装 Docker Desktop
    echo 下载地址: https://www.docker.com/products/docker-desktop/
    pause
    exit /b 1
)
echo [✓] Docker 已安装

echo.
echo [2/3] 启动 Docker 服务...
docker-compose up -d --build

if errorlevel 1 (
    echo [错误] 启动失败，请检查错误信息
    pause
    exit /b 1
)

echo.
echo [3/3] 等待服务启动...
timeout /t 3 /nobreak >nul

echo.
echo ========================================
echo   ✓ 启动成功！
echo ========================================
echo.
echo   请在浏览器中访问: http://localhost:8000
echo.
echo   按任意键打开浏览器...
pause >nul

start http://localhost:8000

echo.
echo 提示：要停止服务，请运行: docker-compose down
echo.
pause
