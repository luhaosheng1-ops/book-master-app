import os
import datetime
import urllib.parse
import fitz  # PyMuPDF
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, FileResponse, StreamingResponse
import json
from dotenv import load_dotenv
from ebooklib import epub
from bs4 import BeautifulSoup
from openai import OpenAI

# 1. 配置加载
load_dotenv()
API_KEY = os.getenv("DEEPSEEK_API_KEY")
OUTPUT_DIR = os.getenv("OUTPUT_DIRECTORY", "/app/output") # 建议 Docker 内部路径固定

if not os.path.exists(OUTPUT_DIR):
    os.makedirs(OUTPUT_DIR, exist_ok=True)

client = OpenAI(api_key=API_KEY, base_url="https://api.deepseek.com/v1")

app = FastAPI()

# 2. CORS 中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

SYSTEM_PROMPT = """你是一位拥有20年经验的顶级战略分析师与知识架构师。
请对提供的文本进行“知识脱水”和“手术刀式解构”，剔除所有煽情和修饰，只保留逻辑干货。

请严格按以下维度输出（Markdown格式）：

一、第一性原理 (Core Philosophy)
- 提取书中最核心、不可再拆分的思维模型或逻辑起点。

二、核心算法与公式 (The Algorithm)
- 提炼书中的定量关系（如：复利公式、估值模型等）。

三、反直觉洞察 (Counter-intuitive Insights)
- 重点列出书中打破常识、挑战认知的核心观点。

四、行动策略 (Actionable SOP)
- 将理论转化为3-5条可立即执行的操作流程或决策清单。

五、硬核证据链 (Evidence Chain)
- 保留关键实验数据、历史事实或硬核案例（拒绝泛泛而谈）。

六、Mermaid 逻辑导图 (Visual Logic)
- 请输出一段 Mermaid 思维导图代码，梳理全书逻辑架构。

输出要求：文字精练，多用列表，严禁使用“本书旨在”等废话。"""

def extract_text_from_any(file_path):
    """万能格式解析"""
    ext = os.path.splitext(file_path)[1].lower()
    text = ""
    try:
        if ext == ".pdf":
            with fitz.open(file_path) as doc:
                # 提取前 30 页，确保有足够干货
                for page in doc[:30]:
                    text += page.get_text()
        elif ext == ".epub":
            book = epub.read_epub(file_path)
            items = list(book.get_items_of_type(9))
            for item in items[:8]: # 增加到8个章节
                soup = BeautifulSoup(item.get_content(), 'html.parser')
                text += soup.get_text()
        elif ext in [".txt", ".md"]:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                text = f.read(25000) # 读取前2.5万字
    except Exception as e:
        print(f"解析出错: {e}")
    return text

# 3. 核心业务接口 - 流式传输版本
@app.post("/analyze")
async def analyze_book(file: UploadFile = File(...)):
    # 保存临时文件
    temp_path = f"temp_{file.filename}"
    try:
        with open(temp_path, "wb") as f:
            f.write(await file.read())
        
        # 提取文字
        book_content = extract_text_from_any(temp_path)
        if not book_content.strip():
            raise HTTPException(status_code=400, detail="无法提取内容，请确保文件未加密")

        # 生成唯一文件名
        timestamp = datetime.datetime.now().strftime("%H%M%S")
        safe_filename = f"解构_{os.path.splitext(file.filename)[0]}_{timestamp}.md"
        full_save_path = os.path.join(OUTPUT_DIR, safe_filename)
        
        # 流式生成器函数
        async def generate_stream():
            accumulated_text = ""
            try:
                # 调用 DeepSeek 流式API
                stream = client.chat.completions.create(
                    model="deepseek-chat",
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": f"请深度解构以下书籍内容：\n\n{book_content[:18000]}"}
                    ],
                    stream=True
                )
                
                # 先发送文件名信息
                yield f"data: {json.dumps({'type': 'filename', 'filename': safe_filename}, ensure_ascii=False)}\n\n"
                
                # 流式接收并转发
                for chunk in stream:
                    if chunk.choices and len(chunk.choices) > 0:
                        delta = chunk.choices[0].delta
                        if hasattr(delta, 'content') and delta.content:
                            content = delta.content
                            accumulated_text += content
                            # 发送内容片段
                            yield f"data: {json.dumps({'type': 'content', 'chunk': content}, ensure_ascii=False)}\n\n"
                
                # 流式传输完成后，保存完整文件
                with open(full_save_path, "w", encoding="utf-8") as f:
                    f.write(accumulated_text)
                
                # 发送完成信号
                yield f"data: {json.dumps({'type': 'done', 'filename': safe_filename}, ensure_ascii=False)}\n\n"
                
            except Exception as e:
                yield f"data: {json.dumps({'type': 'error', 'error': str(e)}, ensure_ascii=False)}\n\n"
            finally:
                if os.path.exists(temp_path):
                    os.remove(temp_path)
        
        return StreamingResponse(
            generate_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no"
            }
        )
    
    except Exception as e:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        raise HTTPException(status_code=500, detail=str(e))
@app.get("/download/{filename}")
async def download_file(filename: str):
    # 解码前端传来的 URL 编码
    real_filename = urllib.parse.unquote(filename)
    
    # 这里的路径一定要和你保存时的 OUTPUT_DIR 绝对一致
    output_dir = os.getenv("OUTPUT_DIRECTORY", "/app/output")
    file_path = os.path.join(output_dir, real_filename)
    
    print(f"DEBUG: 正在尝试下载文件: {file_path}") # 增加调试日志

    if os.path.exists(file_path):
        return FileResponse(
            path=file_path, 
            filename=real_filename,
            # 强制浏览器作为附件下载
            content_disposition_type="attachment"
        )
    else:
        # 如果找不到，返回 404，这样前端控制台能看到具体报错
        raise HTTPException(status_code=404, detail=f"File not found at {file_path}")
# 4. 下载接口
@app.get("/download/{filename}")
async def download_file(filename: str):
    file_path = os.path.join(OUTPUT_DIR, filename)
    if os.path.exists(file_path):
        encoded_filename = urllib.parse.quote(filename)
        return FileResponse(
            path=file_path, 
            filename=filename,
            headers={"Content-Disposition": f"attachment; filename*=utf-8''{encoded_filename}"}
        )
    raise HTTPException(status_code=404, detail="文件不存在")

# 5. 配置查询接口
@app.get("/config")
def get_config():
    return {"current_output_dir": os.path.abspath(OUTPUT_DIR)}

# 6. 前端入口
@app.get("/", response_class=HTMLResponse)
async def read_index():
    index_path = os.path.join("..", "frontend", "index.html")
    if os.path.exists(index_path):
        with open(index_path, "r", encoding="utf-8") as f:
            return f.read()
    return "前端文件 index.html 不存在，请检查路径"