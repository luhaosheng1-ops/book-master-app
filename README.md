# 📘 读书解构大师 (Book Deconstruction Master)

基于 **DeepSeek API** 的电子书深度解构工具，专门针对投资理财与知识类书籍设计。

## 🚀 功能特点
- **全格式支持**：PDF, EPUB, TXT 统统拿下。
- **深度解构**：不仅是总结，更能抠出底层模型、行动 SOP 和硬核案例。
- **本地同步**：解构结果自动以 Markdown 格式保存到你指定的本地目录。
- **一键下载**：支持在浏览器直接下载 MD 文件或打印成 PDF。

## 🛠️ 快速开始

### 前置要求
- Python 3.9+ 或 Docker
- DeepSeek API Key（[获取地址](https://www.deepseek.com/)）

### 方式一：Docker 运行（推荐）

1. **创建 `.env` 文件**（在项目根目录）：
   ```env
   DEEPSEEK_API_KEY=sk-你的API密钥
   OUTPUT_DIRECTORY=./output
   ```

2. **启动服务**：
   ```bash
   docker-compose up -d --build
   ```

3. **访问应用**：
   打开浏览器访问 `http://localhost:8000`

### 方式二：本地运行

1. **安装依赖**：
   ```bash
   cd backend
   pip install -r requirements.txt
   ```

2. **配置 `.env` 文件**（同上）

3. **启动后端**：
   ```bash
   cd backend
   uvicorn main:app --host 0.0.0.0 --port 8000 --reload
   ```

4. **打开前端**：
   直接用浏览器打开 `frontend/index.html` 或使用本地服务器

📖 **详细运行指南请查看 [运行指南.md](./运行指南.md)**

## ✨ 新功能：逐段飞入动画

现在AI解构的内容会**一段一段飞入显示**，让您实时看到AI思考的过程，体验更加有趣！