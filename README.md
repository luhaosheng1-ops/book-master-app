# 📘 读书解构大师 (Book Deconstruction Master)

基于 **DeepSeek API** 的电子书深度解构工具，专门针对投资理财与知识类书籍设计。

## 🚀 功能特点
- **全格式支持**：PDF, EPUB, TXT 统统拿下。
- **深度解构**：不仅是总结，更能抠出底层模型、行动 SOP 和硬核案例。
- **本地同步**：解构结果自动以 Markdown 格式保存到你指定的本地目录。
- **一键下载**：支持在浏览器直接下载 MD 文件或打印成 PDF。

## 🛠️ 快速开始
1. 克隆本项目。

2. 配置 `.env` 文件，填入你的 `DEEPSEEK_API_KEY`。

3. 运行 Docker：
   
   ```
   docker-compose up -d --build
   ```
   
4. 访问 `http://localhost:8000` 即可开始你的深度阅读之旅。