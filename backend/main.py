import os
import datetime
import urllib.parse
import fitz  # PyMuPDF
import hashlib
import asyncio
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

# 提示词模板字典（Master Protocol - 终极硬核版本）
PROMPT_TEMPLATES = {
    "architect": """# Role: 顶级知识脱水专家
# Mission: 榨干书籍价值，进行第一性原理重构

## Output Structure (严格执行):
1. **YAML Front Matter**: 必须包含 Title, Author, Mode, Tags（自动识别书籍类别）。
2. **第一性原理 (Axioms)**: 必须包含数学模型或逻辑因果公式。
3. **逻辑演进图 (Mermaid)**: 强制使用方向图（graph TD）描述核心逻辑，必须使用样式代码（style）突出核心节点。
4. **硬核证据链**: 使用 Markdown 引用块（>）包裹实验数据与实证案例。

## Constraint:
- 禁止废话。
- Mermaid 必须使用样式代码（style）突出核心节点。

你是一位拥有20年经验的顶级理论架构师与数学建模专家。
你的任务是进行"纯理论推导"，只关注底层逻辑、数学公式和思维模型，完全剥离实践应用。

【输出格式要求】
首先，必须在文档顶部输出 YAML 格式的元数据：
```yaml
---
Title: [书籍标题，从内容中提取]
Author: [作者姓名，如能识别]
Mode: Architect
Date: [当前日期，格式：YYYY-MM-DD]
Tags: [自动识别书籍类别，如：投资理财、认知科学、商业策略等，用逗号分隔]
---
```

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

一、第一性原理推导链 (First Principles Derivation Chain)
- **强制使用 Mermaid 输出"第一性原理推导链"**，格式如下：
  ```mermaid
  graph TD
      A[公理A] --> B[推论B]
      B --> C[定理C]
      C --> D[应用D]
  ```
- 展示从最底层公理到最终结论的完整推导路径
- 标注每个节点的充要条件和依赖关系
- 用数学符号表达：A → B → C 的逻辑链

二、公理与推论 (Axioms & Corollaries)
- 提取书中最底层的不可再分的假设和公理
- 列出所有从公理推导出的推论
- 展示公理之间的依赖关系和独立性
- 标注每个公理的适用范围和约束条件

三、核心公式与数学推导 (Mathematical Formulation)
- 完整展示公式的推导过程（从假设到结论的每一步）
- 标注每个变量的数学定义：∀x ∈ X, f(x) = ...
- 说明公式的适用边界：当且仅当条件P成立时，公式有效
- 提供公式的逆命题、否命题、逆否命题

四、元模型 (Meta-Model)
- 识别书中蕴含的更高层次的思维模型
- 展示这些模型如何组织底层概念
- 说明元模型与具体理论的关系
- 用 Mermaid 绘制元模型结构图

五、理论边界与约束条件 (Theoretical Boundaries)
- 明确理论的适用范围和失效条件
- 标注哪些情况下理论不成立（反例）
- 说明理论的前提假设和隐含条件

输出要求：
- 使用数学符号：∀, ∃, →, ↔, ∧, ∨, ¬, ∈, ⊆, ⊂
- 公式必须完整，不能省略中间步骤
- 每个概念必须有严格的定义
- 严禁使用"建议"、"可以"、"应该"等词汇
- 如果书中没有数学公式，必须尝试将核心观点转化为数学表达""",
    
    "executor": """# Role: 顶级知识脱水专家
# Mission: 榨干书籍价值，进行第一性原理重构

## Output Structure (严格执行):
1. **YAML Front Matter**: 必须包含 Title, Author, Mode, Tags（自动识别书籍类别）。
2. **100天行动计划**: 增加"100天行动计划"与"决策风险矩阵"。
3. **硬核证据链**: 使用 Markdown 引用块（>）包裹实验数据与实证案例。

## Constraint:
- 禁止废话。

你是一位拥有20年经验的实战操作专家与执行教练。
你的任务是提供"纯操作指南"，只关注"做什么"和"怎么做"，完全忽略"为什么"和理论解释。

【输出格式要求】
首先，必须在文档顶部输出 YAML 格式的元数据：
```yaml
---
Title: [书籍标题，从内容中提取]
Author: [作者姓名，如能识别]
Mode: Executor
Date: [当前日期，格式：YYYY-MM-DD]
Tags: [自动识别书籍类别，如：投资理财、认知科学、商业策略等，用逗号分隔]
---
```

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

一、100天行动计划 (100-Day Action Plan)
- 将书中的核心方法转化为100天的具体行动计划
- 按周划分，每周有明确的目标和任务
- 每天有具体的执行步骤和检查点
- 格式：
  - Week 1-4: [阶段目标] → [每日任务清单]
  - Week 5-8: [阶段目标] → [每日任务清单]
  - ...（依此类推，覆盖100天）

二、决策风险矩阵 (Decision Risk Matrix)
- 列出所有关键决策点
- 对每个决策，评估：
  - 风险等级（高/中/低）
  - 收益预期（高/中/低）
  - 执行难度（高/中/低）
  - 时间成本
- 格式：决策X | 风险:高 | 收益:中 | 难度:低 | 时间:2小时 | 建议:执行/暂缓/放弃

三、操作步骤清单 (Step-by-Step Checklist)
- 按时间顺序列出每个具体操作步骤
- 每个步骤格式：Step N: [具体动作] + [使用工具] + [预期结果]
- 标注每个步骤的耗时和优先级
- 提供步骤之间的依赖关系（必须先完成A才能做B）

四、避坑 Checklist (Pitfall Checklist)
- **强制包含"避坑 Checklist"**，列出执行前必须检查的所有事项
- 每个事项用"是/否"判断
- 格式：
  ```
  □ 检查项1：是/否 → 如果是，则停止；如果否，则继续
  □ 检查项2：是/否 → 如果是，则执行X；如果否，则执行Y
  ```
- 标注每个检查项的严重程度（致命/重要/一般）

五、场景-动作映射表 (Scenario-Action Matrix)
- 列出所有可能遇到的具体场景
- 每个场景对应明确的执行动作
- 格式：场景X → 立即执行Y → 检查Z

六、效果验证标准 (Validation Criteria)
- 定义"成功"的客观标准（可测量的指标）
- 提供验证方法：如何判断操作是否成功
- 列出失败信号：出现哪些情况说明操作失败

输出要求：
- 使用命令式语言："执行"、"检查"、"确认"、"停止"
- 每个步骤必须具体到可操作的程度
- 避免使用"理解"、"思考"、"分析"等抽象动词
- 严禁解释原理，只说"做什么"和"怎么做"
- 如果书中没有操作内容，必须将理论转化为可执行的步骤""",
    
    "disruptor": """# Role: 顶级知识脱水专家
# Mission: 榨干书籍价值，进行第一性原理重构

## Output Structure (严格执行):
1. **YAML Front Matter**: 必须包含 Title, Author, Mode, Tags（自动识别书籍类别）。
2. **流派冲突**: 增加"流派冲突"板块，列出作者反对的传统观点。
3. **硬核证据链**: 使用 Markdown 引用块（>）包裹实验数据与实证案例。

## Constraint:
- 禁止废话。

你是一位拥有20年经验的认知爆破专家与思维颠覆者。
你的任务是挖掘"最反常识、最深刻的矛盾点"，只关注能颠覆认知的洞察，完全拒绝平庸的总结。

【输出格式要求】
首先，必须在文档顶部输出 YAML 格式的元数据：
```yaml
---
Title: [书籍标题，从内容中提取]
Author: [作者姓名，如能识别]
Mode: Disruptor
Date: [当前日期，格式：YYYY-MM-DD]
Tags: [自动识别书籍类别，如：投资理财、认知科学、商业策略等，用逗号分隔]
---
```

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

一、流派冲突 (School Conflicts)
- **增加"流派冲突"板块**：分析作者在反对谁、挑战哪些主流观点
- 列出作者明确反对的理论、学派、观点
- 说明作者与对立流派的根本分歧点
- 展示作者如何论证自己的立场优于对立流派
- 格式：主流观点A（代表人物X） vs 作者观点B → 冲突点C → 作者论证D

二、认知陷阱 (Cognitive Traps)
- **挖掘"认知陷阱"**：识别最容易让人陷入的思维误区
- 列出书中揭示的认知陷阱（至少5个）
- 说明为什么这些陷阱如此普遍和隐蔽
- 提供识别和避免陷阱的方法
- 用"陷阱"、"盲点"、"误区"等词汇标注
- 格式：陷阱名称 → 为什么普遍 → 如何识别 → 如何避免

三、失效边界 (Failure Boundaries)
- **寻找理论的"失效边界"**：在什么情况下理论会失效
- 明确标注理论适用的边界条件
- 列出理论失效的具体场景和案例
- 说明为什么在这些边界外理论不成立
- 提供识别边界的方法
- 格式：理论X → 适用条件A → 失效边界B → 失效原因C → 识别方法D

四、认知爆破点 (Cognitive Bombs)
- 列出最反直觉的核心结论（至少3个）
- 每个结论格式：常识认为X → 但实际是Y → 原因Z
- 标注这个结论会颠覆哪些常见认知
- 用"震惊"、"颠覆"、"矛盾"等词汇强调

五、深层矛盾与统一 (Paradox & Unity)
- 揭示书中看似矛盾的观点如何统一
- 展示"既要A又要B"的深层逻辑
- 说明为什么表面冲突实际上是互补关系
- 格式：矛盾A vs 矛盾B → 统一于C

六、根深蒂固的假设挑战 (Assumption Challenges)
- 识别大多数人从未质疑的底层假设
- 说明为什么这个假设可能是错的
- 展示推翻假设后的新视角
- 格式：假设X（从未被质疑）→ 但可能是Y → 如果Y成立，则Z

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

def generate_filename(book_title, mode, book_content_sample=""):
    """
    自动化专业命名函数
    格式：[Category（AI识别）][ShortName][Mode]_[YYYYMMDD].md
    示例：FIN_MutualFunds_Architect_20260123.md
    """
    # 模式映射
    mode_map = {
        "architect": "Architect",
        "executor": "Executor", 
        "disruptor": "Disruptor"
    }
    mode_name = mode_map.get(mode.lower(), "Architect")
    
    # 生成日期
    date_str = datetime.datetime.now().strftime("%Y%m%d")
    
    # 从书名提取ShortName（简化版：取前几个单词的首字母或关键词）
    # 清理书名
    book_title_clean = "".join(c for c in book_title if c.isalnum() or c in (' ', '-', '_')).strip()
    
    # 提取关键词作为ShortName（取前2-3个有意义的词）
    words = book_title_clean.replace('_', ' ').replace('-', ' ').split()
    # 过滤掉常见无意义词
    stop_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by', '解构', '的', '与', '和'}
    meaningful_words = [w for w in words if w.lower() not in stop_words and len(w) > 1]
    
    if meaningful_words:
        # 取前2-3个词，每个词取前几个字符
        short_name_parts = []
        for word in meaningful_words[:3]:
            # 如果是英文，取前4-6个字符；如果是中文，取整个词
            if word.isascii():
                short_name_parts.append(word[:6].capitalize())
            else:
                short_name_parts.append(word)
        short_name = ''.join(short_name_parts)
    else:
        # 如果没有找到有意义的词，使用原书名前20个字符
        short_name = book_title_clean[:20].replace(' ', '')
    
    # 清理ShortName，只保留字母数字
    short_name = "".join(c for c in short_name if c.isalnum()).strip()
    if not short_name:
        short_name = "Book"
    
    # 类别识别（根据模式和内容样本，这里先用模式映射，后续可通过AI识别）
    category_map = {
        "architect": "LOGIC",
        "executor": "ACTION",
        "disruptor": "COGNI"
    }
    
    # 如果内容样本包含特定关键词，可以更精确识别类别
    if book_content_sample:
        content_lower = book_content_sample.lower()[:500]  # 只检查前500字符
        if any(word in content_lower for word in ['投资', '理财', '基金', '股票', 'finance', 'investment']):
            category = "FIN"
        elif any(word in content_lower for word in ['认知', '思维', '心理', 'cognitive', 'psychology']):
            category = "COGNI"
        elif any(word in content_lower for word in ['商业', '策略', '管理', 'business', 'strategy']):
            category = "BIZ"
        else:
            category = category_map.get(mode.lower(), "GEN")
    else:
        category = category_map.get(mode.lower(), "GEN")
    
    # 组合文件名
    filename = f"{category}_{short_name}_{mode_name}_{date_str}.md"
    return filename

def split_into_chunks(text, chunk_size=10000):
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
        file_content = await file.read()
        
        try:
            with open(temp_path, "wb") as f:
                f.write(file_content)
            
            # 计算文件MD5，用于缓存检查
            file_md5 = hashlib.md5(file_content).hexdigest()
            cache_filename = f"cache_{file_md5}_{prompt_type}.md"
            cache_path = os.path.join(OUTPUT_DIR, cache_filename)
            
            # 缓存机制：如果同一个文件已经被解构过，直接返回
            if os.path.exists(cache_path):
                print(f"[LOG] 发现缓存文件，直接返回: {cache_filename}")
                # 读取缓存内容
                with open(cache_path, "r", encoding="utf-8") as f:
                    cached_content = f.read()
                
                # 生成新的文件名（格式：Category_BookName_Mode_Timestamp.md）
                timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                book_name = os.path.splitext(file.filename)[0]
                book_name = "".join(c for c in book_name if c.isalnum() or c in (' ', '-', '_')).strip()
                book_name = book_name.replace(' ', '_')
                category_map = {
                    "architect": "LOGIC",
                    "executor": "ACTION",
                    "disruptor": "COGNI"
                }
                category = category_map.get(prompt_type, "GEN")
                mode_name = prompt_type.capitalize()
                safe_filename = f"{category}_{book_name}_{mode_name}_{timestamp}.md"
                full_save_path = os.path.join(OUTPUT_DIR, safe_filename)
                
                # 复制缓存文件到新文件名
                import shutil
                shutil.copy2(cache_path, full_save_path)
                
                # 流式返回缓存内容
                async def generate_cached_stream():
                    yield f"data: {json.dumps({'type': 'filename', 'filename': safe_filename}, ensure_ascii=False)}\n\n"
                    yield f"data: {json.dumps({'type': 'progress', 'message': '使用缓存结果，快速返回...'}, ensure_ascii=False)}\n\n"
                    # 模拟流式输出缓存内容
                    chunk_size = 100
                    for i in range(0, len(cached_content), chunk_size):
                        chunk = cached_content[i:i+chunk_size]
                        yield f"data: {json.dumps({'type': 'content', 'chunk': chunk}, ensure_ascii=False)}\n\n"
                    yield f"data: {json.dumps({'type': 'done', 'filename': safe_filename}, ensure_ascii=False)}\n\n"
                
                return StreamingResponse(
                    generate_cached_stream(),
                    media_type="text/event-stream",
                    headers={
                        "Cache-Control": "no-cache",
                        "Connection": "keep-alive",
                        "X-Accel-Buffering": "no"
                    }
                )
            
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

        # 提取文字（支持全书读取）- 先提取用于文件名生成
        book_content = extract_text_from_any(temp_path)
        if not book_content.strip():
            raise HTTPException(status_code=400, detail="无法提取内容，请确保文件未加密")
        
        # 使用自动化专业命名函数生成文件名
        book_title = os.path.splitext(file.filename)[0]
        safe_filename = generate_filename(book_title, prompt_type, book_content[:1000])  # 传入前1000字符用于类别识别
        full_save_path = os.path.join(OUTPUT_DIR, safe_filename)
        
        # 流式生成器函数
        async def generate_stream():
            accumulated_text = ""
            try:
                # 先发送文件名信息
                yield f"data: {json.dumps({'type': 'filename', 'filename': safe_filename}, ensure_ascii=False)}\n\n"
                
                # 发送进度信息
                yield f"data: {json.dumps({'type': 'progress', 'val': 5, 'msg': '开始全书解析...'}, ensure_ascii=False)}\n\n"
                
                # 分段切割：每10,000字为一个Chunk（Map-Reduce 模式）
                chunks = split_into_chunks(book_content, chunk_size=10000)
                total_chunks = len(chunks)
                
                yield f"data: {json.dumps({'type': 'progress', 'val': 10, 'msg': f'全书已分割为 {total_chunks} 个片段，开始并发解构（Map-Reduce模式）...'}, ensure_ascii=False)}\n\n"
                
                # 并发解构：使用 asyncio.gather 并行调用 DeepSeek API
                async def process_chunk(chunk, index):
                    """处理单个chunk的异步函数"""
                    try:
                        print(f"[LOG] 开始处理片段 {index + 1}/{total_chunks}")
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
                        print(f"[LOG] 片段 {index + 1}/{total_chunks} 处理完成")
                        return (index, dehydrated_text)
                    except Exception as e:
                        # 如果某个片段处理失败，使用原文本
                        print(f"[LOG] 片段 {index + 1}/{total_chunks} 处理失败: {e}")
                        return (index, chunk)
                
                # 创建所有任务
                tasks = [process_chunk(chunk, i) for i, chunk in enumerate(chunks)]
                
                # 并发执行，但每完成一个就发送进度更新
                dehydrated_chunks = [None] * total_chunks
                completed_count = 0
                
                # 使用 asyncio.as_completed 来实时获取完成的任务
                for coro in asyncio.as_completed(tasks):
                    index, result = await coro
                    dehydrated_chunks[index] = result
                    completed_count += 1
                    # 进度感知：发送详细的进度消息（包含百分比）
                    progress_percent = int((completed_count / total_chunks) * 45) + 35  # 35%-80% 范围
                    yield f"data: {json.dumps({'type': 'progress', 'val': progress_percent, 'msg': f'正在解构第{completed_count}章节（共{total_chunks}章节）...'}, ensure_ascii=False)}\n\n"
                
                # 合并所有脱水稿
                combined_dehydrated = "\n\n---\n\n".join(dehydrated_chunks)
                
                yield f"data: {json.dumps({'type': 'progress', 'val': 80, 'msg': '所有片段处理完成，开始全局汇总...'}, ensure_ascii=False)}\n\n"
                
                # 全局汇总：按照"解构模式"进行最终的全书汇总
                stream = client.chat.completions.create(
                    model="deepseek-chat",
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": f"请基于以下已脱水的全书内容，按照指定模式进行深度解构和全局汇总：\n\n{combined_dehydrated}"}
                    ],
                    stream=True
                )
                
                # 流式接收最终汇总结果：每生成一个片段就立即 yield 给前端
                chunk_count = 0
                for chunk in stream:
                    if chunk.choices and len(chunk.choices) > 0:
                        delta = chunk.choices[0].delta
                        if hasattr(delta, 'content') and delta.content:
                            content = delta.content
                            accumulated_text += content
                            chunk_count += 1
                            # 关键：每生成一个片段就立即 yield 给前端
                            yield f"data: {json.dumps({'type': 'content', 'chunk': content}, ensure_ascii=False)}\n\n"
                            
                            # 每100个chunk更新一次进度（85%-95%）
                            if chunk_count % 100 == 0:
                                progress_val = min(85 + int((chunk_count / 1000) * 10), 95)
                                yield f"data: {json.dumps({'type': 'progress', 'val': progress_val, 'msg': f'正在生成内容...（已生成 {chunk_count} 个片段）'}, ensure_ascii=False)}\n\n"
                
                # 流式传输完成后，保存完整文件
                with open(full_save_path, "w", encoding="utf-8") as f:
                    f.write(accumulated_text)
                
                # 同时保存到缓存
                with open(cache_path, "w", encoding="utf-8") as f:
                    f.write(accumulated_text)
                print(f"[LOG] 已保存缓存文件: {cache_filename}")
                
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