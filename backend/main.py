import os
import datetime
import urllib.parse
import fitz  # PyMuPDF
from fastapi import FastAPI, UploadFile, File, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, FileResponse, StreamingResponse
import json
from dotenv import load_dotenv
from ebooklib import epub
from bs4 import BeautifulSoup
from openai import OpenAI
import httpx
from httpx import ConnectError, TimeoutException, RequestError, ReadTimeout, ConnectTimeout

# 1. 配置加载
load_dotenv()
API_KEY = os.getenv("DEEPSEEK_API_KEY")
OUTPUT_DIR = os.getenv("OUTPUT_DIRECTORY", "/app/output") # 建议 Docker 内部路径固定

if not os.path.exists(OUTPUT_DIR):
    os.makedirs(OUTPUT_DIR, exist_ok=True)

# 配置 httpx 异步客户端，设置超时和代理
# 在本地测试环境下，优先尝试直连 api.deepseek.com 而非强制走系统代理
# 设置 proxies=None 可以：
# 1. 绕过系统代理设置，避免代理不稳定导致的连接问题
# 2. 优先直连 api.deepseek.com，提高连接速度和稳定性
# 3. 如果确实需要代理，可以通过环境变量 HTTP_PROXY 或 HTTPS_PROXY 设置
http_client = httpx.AsyncClient(
    timeout=httpx.Timeout(300.0, connect=30.0),  # 总超时300秒，连接超时30秒（支持全书解构）
    proxies=None,  # 显式禁用代理，避免不稳定的系统代理，优先直连
    limits=httpx.Limits(max_keepalive_connections=5, max_connections=10),
    follow_redirects=True
)

# 初始化 OpenAI 客户端，使用自定义 http_client
client = OpenAI(
    api_key=API_KEY,
    base_url="https://api.deepseek.com/v1",
    http_client=http_client
)

app = FastAPI()

# 2. CORS 中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# 提示词模板字典（带负向约束，强化模式差异）
PROMPT_TEMPLATES = {
    "architect": """你是一位拥有20年经验的顶级理论架构师与数学建模专家。
你的任务是进行"纯理论推导"，只关注底层逻辑、数学公式和思维模型，完全剥离实践应用。

【严格禁止】
❌ 禁止输出任何行动建议、操作步骤、实践指南
❌ 禁止提供"如何做"、"应该怎么做"等执行性内容
❌ 禁止列出清单、检查表、决策树等操作工具
❌ 禁止描述应用场景、使用案例、实践效果
❌ 禁止使用"建议"、"可以"、"应该"等指导性词汇

【必须强化】
✅ 必须展示完整的数学公式推导过程
✅ 必须标注每个变量的定义域、值域和约束条件
✅ 必须梳理从公理到定理的完整逻辑链条
✅ 必须识别理论边界和适用前提
✅ 必须用数学符号和逻辑符号表达关系

请严格按以下维度输出（Markdown格式）：

一、第一性原理与公理体系 (Axioms & First Principles)
- 提取最底层的不可再分的假设和公理
- 展示公理之间的依赖关系和独立性
- 用数学符号表达：A → B → C 的逻辑链

二、核心公式与数学推导 (Mathematical Formulation)
- 完整展示公式的推导过程（从假设到结论的每一步）
- 标注每个变量的数学定义：∀x ∈ X, f(x) = ...
- 说明公式的适用边界：当且仅当条件P成立时，公式有效
- 提供公式的逆命题、否命题、逆否命题

三、逻辑结构图 (Logical Structure)
- 用 Mermaid 代码绘制完整的逻辑依赖图
- 展示概念之间的蕴含关系、等价关系、互斥关系
- 标注每个节点的充要条件
- **重要**：Mermaid 代码必须包裹在标准代码块中，格式如下：
  ```mermaid
  graph TD
      A[概念A] --> B[概念B]
      B --> C[概念C]
  ```

四、理论边界与约束条件 (Theoretical Boundaries)
- 明确理论的适用范围和失效条件
- 标注哪些情况下理论不成立（反例）
- 说明理论的前提假设和隐含条件

五、抽象层次与泛化 (Abstraction & Generalization)
- 展示从具体到抽象的层次结构
- 说明理论的泛化能力和推广边界

输出要求：
- 使用数学符号：∀, ∃, →, ↔, ∧, ∨, ¬, ∈, ⊆, ⊂
- 公式必须完整，不能省略中间步骤
- 每个概念必须有严格的定义
- 严禁使用"建议"、"可以"、"应该"等词汇
- 如果书中没有数学公式，必须尝试将核心观点转化为数学表达""",
    
    "executor": """你是一位拥有20年经验的实战操作专家与执行教练。
你的任务是提供"纯操作指南"，只关注"做什么"和"怎么做"，完全忽略"为什么"和理论解释。

【严格禁止】
❌ 禁止解释底层原理、理论依据、数学推导
❌ 禁止说明"为什么这样做"、"背后的逻辑是什么"
❌ 禁止描述思维模型、认知框架、理论体系
❌ 禁止讨论概念定义、公理假设、逻辑关系
❌ 禁止使用"因为"、"由于"、"原理是"等解释性词汇

【必须强化】
✅ 必须提供可立即执行的步骤序列（Step 1, Step 2, Step 3...）
✅ 必须使用决策树格式：如果条件A，则执行B；否则执行C
✅ 必须列出检查清单（Checklist）格式
✅ 必须标注每个步骤的具体操作、时间、地点、工具
✅ 必须提供"做/不做"的二元判断标准

请严格按以下维度输出（Markdown格式）：

一、操作步骤清单 (Step-by-Step Checklist)
- 按时间顺序列出每个具体操作步骤
- 每个步骤格式：Step N: [具体动作] + [使用工具] + [预期结果]
- 标注每个步骤的耗时和优先级
- 提供步骤之间的依赖关系（必须先完成A才能做B）

二、决策树 (Decision Tree)
```
如果 [条件1]：
    ├─ 是 → 执行 [动作A]
    └─ 否 → 如果 [条件2]：
            ├─ 是 → 执行 [动作B]
            └─ 否 → 执行 [动作C]
```

三、场景-动作映射表 (Scenario-Action Matrix)
- 列出所有可能遇到的具体场景
- 每个场景对应明确的执行动作
- 格式：场景X → 立即执行Y → 检查Z

四、避坑检查清单 (Pitfall Checklist)
- 列出执行前必须检查的N个事项
- 每个事项用"是/否"判断
- 格式：□ 检查项1：是/否 → 如果是，则停止；如果否，则继续

五、效果验证标准 (Validation Criteria)
- 定义"成功"的客观标准（可测量的指标）
- 提供验证方法：如何判断操作是否成功
- 列出失败信号：出现哪些情况说明操作失败

输出要求：
- 使用命令式语言："执行"、"检查"、"确认"、"停止"
- 每个步骤必须具体到可操作的程度
- 避免使用"理解"、"思考"、"分析"等抽象动词
- 严禁解释原理，只说"做什么"和"怎么做"
- 如果书中没有操作内容，必须将理论转化为可执行的步骤""",
    
    "disruptor": """你是一位拥有20年经验的认知爆破专家与思维颠覆者。
你的任务是挖掘"最反常识、最深刻的矛盾点"，只关注能颠覆认知的洞察，完全拒绝平庸的总结。

【严格禁止】
❌ 禁止输出常规总结、表面描述、常识性观点
❌ 禁止列出"大家都知道"的内容
❌ 禁止提供平衡、中性的观点（必须选边站）
❌ 禁止使用"可能"、"或许"、"一般来说"等模糊表达
❌ 禁止重复书中显而易见的结论

【必须强化】
✅ 必须挖掘与直觉完全相反的结论
✅ 必须揭示表面矛盾背后的深层统一
✅ 必须挑战最根深蒂固的认知假设
✅ 必须用"但是"、"然而"、"实际上"等转折词
✅ 必须提供"大多数人认为X，但实际上是Y"的对比

请严格按以下维度输出（Markdown格式）：

一、认知爆破点 (Cognitive Bombs)
- 列出最反直觉的核心结论（至少3个）
- 每个结论格式：常识认为X → 但实际是Y → 原因Z
- 标注这个结论会颠覆哪些常见认知
- 用"震惊"、"颠覆"、"矛盾"等词汇强调

二、深层矛盾与统一 (Paradox & Unity)
- 揭示书中看似矛盾的观点如何统一
- 展示"既要A又要B"的深层逻辑
- 说明为什么表面冲突实际上是互补关系
- 格式：矛盾A vs 矛盾B → 统一于C

三、根深蒂固的假设挑战 (Assumption Challenges)
- 识别大多数人从未质疑的底层假设
- 说明为什么这个假设可能是错的
- 展示推翻假设后的新视角
- 格式：假设X（从未被质疑）→ 但可能是Y → 如果Y成立，则Z

四、认知陷阱与盲点 (Cognitive Traps)
- 列出最容易陷入的思维误区
- 说明为什么这些误区如此普遍
- 提供识别和避免陷阱的方法
- 用"陷阱"、"盲点"、"误区"等词汇标注

五、颠覆性论证 (Disruptive Arguments)
- 展示最有力的反常识论证
- 列出支持反常识的证据链
- 说明为什么反常识的观点更合理
- 格式：传统观点A → 论证过程 → 反常识结论B（更合理）

输出要求：
- 每个观点必须带有"但是"、"然而"、"实际上"等转折
- 使用强烈的对比："不是X，而是Y"
- 避免中庸表达，必须选边站
- 严禁总结常识，只挖掘反常识
- 如果书中没有反常识内容，必须质疑书中的核心假设"""
}

def extract_text_from_any(file_path):
    """万能格式解析 - 支持全书读取"""
    ext = os.path.splitext(file_path)[1].lower()
    text = ""
    try:
        if ext == ".pdf":
            with fitz.open(file_path) as doc:
                # 提取全书内容，不再限制页数
                for page in doc:
                    text += page.get_text()
        elif ext == ".epub":
            book = epub.read_epub(file_path)
            items = list(book.get_items_of_type(9))
            # 提取所有章节，不再限制数量
            for item in items:
                soup = BeautifulSoup(item.get_content(), 'html.parser')
                text += soup.get_text()
        elif ext in [".txt", ".md"]:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                text = f.read()  # 读取全部内容，不再限制长度
    except Exception as e:
        print(f"解析出错: {e}")
    return text

def split_into_chunks(text, chunk_size=12000):
    """将文本按指定大小分割成多个块"""
    chunks = []
    current_chunk = ""
    
    # 按段落分割，尽量在段落边界处切割
    paragraphs = text.split('\n\n')
    
    for para in paragraphs:
        # 如果当前块加上新段落不超过限制，则添加
        if len(current_chunk) + len(para) + 2 <= chunk_size:
            current_chunk += para + '\n\n'
        else:
            # 如果当前块不为空，保存它
            if current_chunk.strip():
                chunks.append(current_chunk.strip())
            # 如果单个段落就超过限制，强制切割
            if len(para) > chunk_size:
                # 按字符强制切割
                for i in range(0, len(para), chunk_size):
                    chunks.append(para[i:i+chunk_size])
                current_chunk = ""
            else:
                current_chunk = para + '\n\n'
    
    # 添加最后一个块
    if current_chunk.strip():
        chunks.append(current_chunk.strip())
    
    return chunks

# 3. 核心业务接口 - 流式传输版本
@app.post("/analyze")
async def analyze_book(
    file: UploadFile = File(...),
    prompt_type: str = Query("architect", description="提示词类型: architect, executor, disruptor")
):
    # 保存临时文件
    temp_path = f"temp_{file.filename}"
    try:
        with open(temp_path, "wb") as f:
            f.write(await file.read())
        
        # 提取文字（支持全书读取）
        book_content = extract_text_from_any(temp_path)
        if not book_content.strip():
            raise HTTPException(status_code=400, detail="无法提取内容，请确保文件未加密")

        # 验证并获取提示词
        if prompt_type not in PROMPT_TEMPLATES:
            raise HTTPException(status_code=400, detail=f"无效的提示词类型: {prompt_type}。可选值: architect, executor, disruptor")
        
        system_prompt = PROMPT_TEMPLATES[prompt_type]
        
        # 生成初步脱水提示词（用于分段解构）
        preliminary_prompt = """你是一位知识提取专家。请对提供的文本片段进行"初步脱水"：
1. 提取核心观点和关键信息
2. 保留重要的数据、公式、案例
3. 去除冗余描述和修饰性语言
4. 保持逻辑结构清晰
5. 输出格式为简洁的 Markdown

请开始脱水："""

        # 生成唯一文件名
        timestamp = datetime.datetime.now().strftime("%H%M%S")
        safe_filename = f"解构_{os.path.splitext(file.filename)[0]}_{timestamp}.md"
        full_save_path = os.path.join(OUTPUT_DIR, safe_filename)
        
        # 流式生成器函数
        async def generate_stream():
            accumulated_text = ""
            try:
                # 先发送文件名信息
                yield f"data: {json.dumps({'type': 'filename', 'filename': safe_filename}, ensure_ascii=False)}\n\n"
                
                # 发送进度信息
                yield f"data: {json.dumps({'type': 'progress', 'message': '开始全书解析...'}, ensure_ascii=False)}\n\n"
                
                # 分段切割：每12,000字为一个Chunk
                chunks = split_into_chunks(book_content, chunk_size=12000)
                total_chunks = len(chunks)
                
                yield f"data: {json.dumps({'type': 'progress', 'message': f'全书已分割为 {total_chunks} 个片段，开始分段解构...'}, ensure_ascii=False)}\n\n"
                
                # 循环解构：对每个Chunk调用API进行初步脱水
                dehydrated_chunks = []
                for i, chunk in enumerate(chunks, 1):
                    yield f"data: {json.dumps({'type': 'progress', 'message': f'正在处理第 {i}/{total_chunks} 个片段...'}, ensure_ascii=False)}\n\n"
                    
                    try:
                        # 调用 DeepSeek API 进行初步脱水（非流式，因为需要完整结果）
                        response = await client.chat.completions.create(
                            model="deepseek-chat",
                            messages=[
                                {"role": "system", "content": preliminary_prompt},
                                {"role": "user", "content": f"请对以下文本片段进行初步脱水：\n\n{chunk}"}
                            ],
                            stream=False
                        )
                        
                        dehydrated_text = response.choices[0].message.content
                        dehydrated_chunks.append(dehydrated_text)
                        
                    except Exception as e:
                        # 如果某个片段处理失败，使用原文本
                        print(f"片段 {i} 处理失败: {e}")
                        dehydrated_chunks.append(chunk)
                
                # 合并所有脱水稿
                combined_dehydrated = "\n\n---\n\n".join(dehydrated_chunks)
                
                yield f"data: {json.dumps({'type': 'progress', 'message': '所有片段处理完成，开始全局汇总...'}, ensure_ascii=False)}\n\n"
                
                # 全局汇总：按照"解构模式"进行最终的全书汇总
                stream = client.chat.completions.create(
                    model="deepseek-chat",
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": f"请基于以下已脱水的全书内容，按照指定模式进行深度解构和全局汇总：\n\n{combined_dehydrated}"}
                    ],
                    stream=True
                )
                
                # 流式接收最终汇总结果
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
                
            except ConnectError as e:
                # 连接错误：可能是网络问题或代理问题
                error_msg = "无法连接到 DeepSeek API。请检查：\n1. 网络连接是否正常\n2. VPN 状态是否正确\n3. 防火墙设置是否阻止了连接"
                print(f"连接错误: {e}")
                yield f"data: {json.dumps({'type': 'error', 'error': error_msg}, ensure_ascii=False)}\n\n"
            except (TimeoutException, ReadTimeout, ConnectTimeout) as e:
                # 超时错误：可能是代理超时或网络慢
                timeout_type = type(e).__name__
                error_msg = f"API 请求超时 ({timeout_type})。请检查：\n1. 网络连接是否稳定\n2. VPN 是否正常工作\n3. 代理设置是否正确（建议直连 api.deepseek.com）"
                print(f"超时错误: {e}")
                yield f"data: {json.dumps({'type': 'error', 'error': error_msg}, ensure_ascii=False)}\n\n"
            except RequestError as e:
                # 请求错误：可能是代理或其他网络问题
                error_msg = f"网络请求失败。请检查网络连接或 VPN 状态。错误详情: {str(e)}"
                print(f"请求错误: {e}")
                yield f"data: {json.dumps({'type': 'error', 'error': error_msg}, ensure_ascii=False)}\n\n"
            except Exception as e:
                # 其他异常
                error_type = type(e).__name__
                error_msg = f"API 调用失败 ({error_type}): {str(e)}"
                print(f"API 调用异常: {e}")
                yield f"data: {json.dumps({'type': 'error', 'error': error_msg}, ensure_ascii=False)}\n\n"
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