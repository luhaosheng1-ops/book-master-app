import os
import datetime
import urllib.parse
import fitz  # PyMuPDF
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, FileResponse
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

SYSTEM_PROMPT = """你是一位顶尖的投资分析师和知识管理专家，精通深度解构各类书籍。
请不要进行泛泛的总结，而是进行“手术刀式”的解构。请严格按照以下模块输出（Markdown格式）：
一、核心模型：提取最底层的思维模型或公式
二、关键证据：保留硬核数据、实验案例或事实
三、核心概念：深度解析书中的专业名词
四、行动策略：转化为3-5条可执行的SOP流程
五、知识地图：梳理章节间的底层逻辑演进
"""

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

# 3. 核心业务接口
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

        # 调用 DeepSeek
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"请深度解构以下书籍内容：\n\n{book_content[:18000]}"} # 限制发送长度，防报错
            ],
            stream=False
        )
        
        result_text = response.choices[0].message.content
        
        # 生成唯一文件名
        timestamp = datetime.datetime.now().strftime("%H%M%S")
        safe_filename = f"解构_{os.path.splitext(file.filename)[0]}_{timestamp}.md"
        full_save_path = os.path.join(OUTPUT_DIR, safe_filename)
        
        # 写入本地保存
        with open(full_save_path, "w", encoding="utf-8") as f:
            f.write(result_text)
        
        # 返回给前端（确保字段名与前端对应）
        return {
            "status": "success", 
            "content": result_text, 
            "filename": safe_filename,
            "save_path": full_save_path
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)

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