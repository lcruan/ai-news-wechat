import os
import re
import json
import time
import socket
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta


# ============================================================
# 基础配置
# ============================================================

SILICONFLOW_API_KEY = os.environ.get("SILICONFLOW_API_KEY")

SILICONFLOW_URL = "https://api.siliconflow.cn/v1/chat/completions"

MODEL = "Qwen/Qwen3-8B"

# 按之前已经验证成功的配置保留
REQUEST_TIMEOUT = 120
MAX_RETRIES = 3
RETRY_WAIT_SECONDS = 5

MAX_NEWS_PER_SOURCE = 20

MAX_SCREENING_SUMMARY_CHARS = 800
MAX_FACT_SUMMARY_CHARS = 2000
MAX_ARTICLE_SUMMARY_CHARS = 2500
MAX_SCREENING_CONTEXT_CHARS = 30000

# 最终最多生成多少篇候选
MAX_CANDIDATES = 5


# ============================================================
# RSS 信息源
# ============================================================

RSS_SOURCES = {
    "Ars Technica": "https://feeds.arstechnica.com/arstechnica/technology-lab",
    "MIT Technology Review": "https://www.technologyreview.com/feed/",
}


# ============================================================
# 内容类型
# ============================================================

CONTENT_TYPES = {
    "ai_news": "AI新闻",
    "ai_technology": "AI技术",
    "ai_application": "AI应用",
    "ai_frontend": "AI × 前端",
}


# ============================================================
# 基础文本处理
# ============================================================

def clean_text(text):
    if not text:
        return ""

    text = re.sub(r"<[^>]+>", " ", text)

    text = text.replace("&nbsp;", " ")
    text = text.replace("&amp;", "&")
    text = text.replace("&lt;", "<")
    text = text.replace("&gt;", ">")
    text = text.replace("&quot;", '"')
    text = text.replace("&#39;", "'")

    text = re.sub(r"\s+", " ", text)

    return text.strip()


def truncate_text(text, max_chars):
    text = text or ""

    if len(text) <= max_chars:
        return text

    return text[:max_chars] + "..."


def get_beijing_date():
    beijing_tz = timezone(timedelta(hours=8))

    return datetime.now(
        beijing_tz
    ).strftime("%Y-%m-%d")


# ============================================================
# RSS 抓取
# ============================================================

def fetch_rss(source_name, url):

    print("")
    print("=" * 60)
    print(f"开始抓取 RSS：{source_name}")
    print(url)
    print("=" * 60)

    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 AI-News-Bot/1.0"
        }
    )

    try:

        with urllib.request.urlopen(
            request,
            timeout=REQUEST_TIMEOUT
        ) as response:

            data = response.read()

        print(
            f"{source_name} RSS 获取成功："
            f"{len(data)} bytes"
        )

    except Exception as e:

        print(
            f"{source_name} RSS 获取失败：{e}"
        )

        return []

    try:

        root = ET.fromstring(data)

    except Exception as e:

        print(
            f"{source_name} RSS XML 解析失败：{e}"
        )

        return []

    news_list = []

    # ========================================================
    # RSS 2.0
    # ========================================================

    items = root.findall(".//item")

    for item in items[:MAX_NEWS_PER_SOURCE]:

        title = item.findtext(
            "title",
            ""
        )

        summary = item.findtext(
            "description",
            ""
        )

        link = item.findtext(
            "link",
            ""
        )

        pub_date = item.findtext(
            "pubDate",
            ""
        )

        title = clean_text(title)
        summary = clean_text(summary)
        link = clean_text(link)
        pub_date = clean_text(pub_date)

        if not title or not link:
            continue

        news_list.append({
            "source": source_name,
            "title": title,
            "summary": truncate_text(
                summary,
                MAX_FACT_SUMMARY_CHARS
            ),
            "link": link,
            "pub_date": pub_date,
        })

    # ========================================================
    # Atom
    # ========================================================

    if not news_list:

        atom_entries = root.findall(
            ".//{http://www.w3.org/2005/Atom}entry"
        )

        for entry in atom_entries[
            :MAX_NEWS_PER_SOURCE
        ]:

            title_node = entry.find(
                "{http://www.w3.org/2005/Atom}title"
            )

            summary_node = entry.find(
                "{http://www.w3.org/2005/Atom}summary"
            )

            published_node = entry.find(
                "{http://www.w3.org/2005/Atom}published"
            )

            updated_node = entry.find(
                "{http://www.w3.org/2005/Atom}updated"
            )

            link = ""

            for link_node in entry.findall(
                "{http://www.w3.org/2005/Atom}link"
            ):

                href = link_node.attrib.get(
                    "href",
                    ""
                )

                rel = link_node.attrib.get(
                    "rel",
                    ""
                )

                if href and (
                    not rel
                    or rel == "alternate"
                ):

                    link = href

                    break

            title = clean_text(
                title_node.text
                if title_node is not None
                else ""
            )

            summary = clean_text(
                summary_node.text
                if summary_node is not None
                else ""
            )

            pub_date = ""

            if published_node is not None:

                pub_date = clean_text(
                    published_node.text
                )

            if not pub_date and updated_node is not None:

                pub_date = clean_text(
                    updated_node.text
                )

            if not title or not link:
                continue

            news_list.append({
                "source": source_name,
                "title": title,
                "summary": truncate_text(
                    summary,
                    MAX_FACT_SUMMARY_CHARS
                ),
                "link": link,
                "pub_date": pub_date,
            })

    print(
        f"{source_name} 共抓取 "
        f"{len(news_list)} 条内容"
    )

    return news_list


# ============================================================
# SiliconFlow HTTP
# ============================================================

def is_retryable_http_status(status):

    return status in {
        429,
        500,
        502,
        503,
        504
    }


def call_ai(messages):

    if not SILICONFLOW_API_KEY:

        raise RuntimeError(
            "没有找到 SILICONFLOW_API_KEY 环境变量"
        )

    payload = {
        "model": MODEL,
        "messages": messages,
        "temperature": 0.2,
        "enable_thinking": False
    }

    body = json.dumps(
        payload,
        ensure_ascii=False
    ).encode("utf-8")

    last_error = None

    for attempt in range(
        1,
        MAX_RETRIES + 1
    ):

        print("")

        print(
            f"正在调用 SiliconFlow，"
            f"第 {attempt}/{MAX_RETRIES} 次..."
        )

        request = urllib.request.Request(
            SILICONFLOW_URL,
            data=body,
            headers={
                "Authorization":
                    f"Bearer {SILICONFLOW_API_KEY}",

                "Content-Type":
                    "application/json",

                "User-Agent":
                    "AI-News-WeChat/1.0"
            },
            method="POST"
        )

        try:

            with urllib.request.urlopen(
                request,
                timeout=REQUEST_TIMEOUT
            ) as response:

                response_data = response.read()

            result = json.loads(
                response_data.decode(
                    "utf-8"
                )
            )

            if "error" in result:

                raise RuntimeError(
                    "SiliconFlow API 返回错误："
                    f"{result['error']}"
                )

            choices = result.get(
                "choices",
                []
            )

            if not choices:

                raise RuntimeError(
                    "SiliconFlow 返回结果中没有 choices"
                )

            content = (
                choices[0]
                .get("message", {})
                .get("content", "")
            )

            if not content:

                raise RuntimeError(
                    "SiliconFlow 返回内容为空"
                )

            print(
                "SiliconFlow 调用成功"
            )

            return content.strip()

        except urllib.error.HTTPError as e:

            last_error = e

            try:

                error_body = e.read().decode(
                    "utf-8",
                    errors="ignore"
                )

            except Exception:

                error_body = ""

            print(
                "SiliconFlow HTTP 错误："
                f"{e.code} {error_body}"
            )

            if not is_retryable_http_status(
                e.code
            ):

                raise RuntimeError(
                    "SiliconFlow 请求失败："
                    f"HTTP {e.code} "
                    f"{error_body}"
                )

        except (
            urllib.error.URLError,
            TimeoutError,
            socket.timeout
        ) as e:

            last_error = e

            print(
                "SiliconFlow 请求超时或网络错误："
                f"{e}"
            )

        except Exception as e:

            last_error = e

            print(
                f"SiliconFlow 请求失败：{e}"
            )

        if attempt < MAX_RETRIES:

            print(
                f"{RETRY_WAIT_SECONDS} 秒后自动重试..."
            )

            time.sleep(
                RETRY_WAIT_SECONDS
            )

    raise RuntimeError(
        f"SiliconFlow 连续 "
        f"{MAX_RETRIES} 次请求失败："
        f"{last_error}"
    )


# ============================================================
# 构造内容上下文
# ============================================================

def build_news_context(
    news_list,
    summary_limit
):

    blocks = []

    for index, news in enumerate(
        news_list,
        start=1
    ):

        block = (
            f"内容编号：{index}\n"
            f"来源：{news['source']}\n"
            f"标题：{news['title']}\n"
            f"发布时间：{news['pub_date']}\n"
            f"原文链接：{news['link']}\n"
            f"RSS摘要："
            f"{truncate_text(news['summary'], summary_limit)}"
        )

        blocks.append(block)

    context = "\n\n".join(blocks)

    return truncate_text(
        context,
        MAX_SCREENING_CONTEXT_CHARS
    )


# ============================================================
# 第一步：AI 选择今天的内容方向
# ============================================================

def ask_ai(news_list):

    context = build_news_context(
        news_list,
        MAX_SCREENING_SUMMARY_CHARS
    )

    prompt = f"""
你现在是微信公众号「web前端开发之旅」的主编。

这个公众号不是单纯的 AI 新闻号。

它主要关注：

1. AI技术
2. AI应用
3. AI新闻
4. AI × Web前端

内容比例大致希望保持：

- 40% AI技术
- 30% AI应用
- 20% AI新闻
- 10% AI × 前端

但这不是硬性限制。

最重要的是：

每天只选择一个真正值得写的主题。

==================================================
你的任务
==================================================

从下面提供的 RSS 内容中：

选择今天最值得写成一篇微信公众号文章的内容。

你首先需要判断它属于：

ai_news
ai_technology
ai_application
ai_frontend

四种类型中的哪一种。

然后给出评分。

==================================================
四种内容类型定义
==================================================

【ai_news】

适合：

- AI模型重大发布
- AI产品重大更新
- AI公司重大动作
- AI安全事件
- AI行业重要事件
- 其他具有明显新闻价值的AI事件

【ai_technology】

适合：

- AI模型技术
- Agent
- RAG
- 推理
- 多模态
- AI编程
- 模型训练
- AI工程实践
- 开发工具
- AI基础设施
- 技术原理或技术实践

【ai_application】

适合：

- AI在真实业务中的应用
- AI工具
- AI工作流
- AI办公
- AI开发应用
- AI产品使用场景
- AI提高工作效率的实际案例

【ai_frontend】

适合：

- AI × Web前端
- AI辅助前端开发
- AI生成UI
- AI Coding
- 前端工程与AI结合
- Vue / React / JavaScript 与AI结合
- AI对前端开发流程的影响

==================================================
筛选原则
==================================================

第一优先级：

真正有价值。

第二优先级：

与公众号「web前端开发之旅」读者有关。

第三优先级：

信息明确，能够写出完整文章。

第四优先级：

具有一定的新鲜度。

不要为了追求“新闻”而选择普通内容。

例如：

如果今天没有特别重要的AI新闻，
但有一篇非常值得开发者阅读的AI技术内容，

那么应该选择AI技术。

==================================================
严格事实规则
==================================================

你只能根据下面提供的：

- 标题
- RSS摘要
- 来源
- 发布时间
- 原文链接

进行判断。

绝对不能根据你自己的知识补充事实。

不要因为你“知道这件事情”
就添加输入中不存在的信息。

==================================================
排除内容
==================================================

排除：

- 普通科技新闻
- 与AI关系很弱的内容
- 新闻汇总
- newsletter
- roundup
- 周报
- 每周新闻合集
- 重复报道
- 内容过于空泛的文章

==================================================
评分
==================================================

score 使用 0～10 分。

参考：

9～10：
非常值得今天写。

8～8.9：
值得重点考虑。

7～7.9：
有一定价值。

低于7：
不建议作为今天主选题。

评分考虑：

- 内容价值
- 与公众号读者相关性
- 信息完整程度
- 新鲜度
- 可写性

==================================================
重复事件
==================================================

如果多个来源实际上描述同一个事件：

使用相同的 duplicate_group。

程序之后会进行去重。

==================================================
最多返回5个候选
==================================================

按照优先级排序。

==================================================
输出格式
==================================================

只输出合法 JSON。

不要输出解释。

格式：

[
  {{
    "index": 1,
    "content_type": "ai_technology",
    "is_ai": true,
    "score": 9.2,
    "duplicate_group": "事件或主题名称",
    "reason": "只能根据输入内容说明为什么值得写"
  }}
]

新闻内容：

{context}
"""

    result = call_ai([
        {
            "role": "system",
            "content": (
                "你是一个严谨的AI内容主编。"
                "只能使用输入内容进行判断。"
                "禁止补充外部事实。"
            )
        },
        {
            "role": "user",
            "content": prompt
        }
    ])

    return result


# ============================================================
# JSON 提取
# ============================================================

def extract_json(text):

    text = text.strip()

    text = re.sub(
        r"^```(?:json)?\s*",
        "",
        text,
        flags=re.IGNORECASE
    )

    text = re.sub(
        r"\s*```$",
        "",
        text
    )

    # 优先寻找数组
    start = text.find("[")
    end = text.rfind("]")

    if start != -1 and end != -1:

        candidate = text[
            start:end + 1
        ]

        try:

            return json.loads(
                candidate
            )

        except Exception:
            pass

    # 再寻找对象
    start = text.find("{")
    end = text.rfind("}")

    if start != -1 and end != -1:

        candidate = text[
            start:end + 1
        ]

        try:

            return json.loads(
                candidate
            )

        except Exception:
            pass

    raise ValueError(
        "AI 返回内容无法解析为 JSON：\n"
        f"{text}"
    )


# ============================================================
# 程序二次过滤
# ============================================================

def filter_selected_news(
    ai_result,
    news_list
):

    if isinstance(
        ai_result,
        dict
    ):

        candidates = ai_result.get(
            "candidates",
            []
        )

    else:

        candidates = ai_result

    if not isinstance(
        candidates,
        list
    ):

        return None

    valid = []

    used_duplicate_groups = set()

    roundup_keywords = [
        "roundup",
        "newsletter",
        "weekly",
        "this week",
        "daily roundup",
        "news roundup",
        "weekly roundup"
    ]

    for item in candidates:

        if not isinstance(
            item,
            dict
        ):
            continue

        try:

            index = int(
                item.get(
                    "index",
                    0
                )
            )

        except Exception:

            continue

        if (
            index < 1
            or index > len(news_list)
        ):

            continue

        if item.get(
            "is_ai"
        ) is not True:

            continue

        try:

            score = float(
                item.get(
                    "score",
                    0
                )
            )

        except Exception:

            score = 0

        if score < 7:

            continue

        duplicate_group = str(
            item.get(
                "duplicate_group",
                ""
            )
        ).strip()

        if duplicate_group:

            if duplicate_group in (
                used_duplicate_groups
            ):

                continue

            used_duplicate_groups.add(
                duplicate_group
            )

        news = news_list[
            index - 1
        ]

        title = news[
            "title"
        ].lower()

        if any(
            keyword in title
            for keyword in roundup_keywords
        ):

            continue

        content_type = str(
            item.get(
                "content_type",
                "ai_news"
            )
        ).strip()

        if content_type not in CONTENT_TYPES:

            content_type = (
                "ai_news"
            )

        valid.append({
            "news": news,
            "score": score,
            "reason": str(
                item.get(
                    "reason",
                    ""
                )
            ).strip(),
            "content_type": content_type
        })

    if not valid:

        return None

    valid.sort(
        key=lambda x: x["score"],
        reverse=True
    )

    return valid[0]


# ============================================================
# 第二步：提取事实
# ============================================================

def extract_facts(news):

    summary = truncate_text(
        news["summary"],
        MAX_FACT_SUMMARY_CHARS
    )

    prompt = f"""
你现在负责给微信公众号文章提取事实依据。

只能使用下面这一条RSS内容。

来源：
{news['source']}

标题：
{news['title']}

发布时间：
{news['pub_date']}

RSS摘要：
{summary}

原文链接：
{news['link']}

==================================================
任务
==================================================

最多提取5条明确事实。

每一条事实都必须能够直接从输入内容确认。

如果输入没有明确说明，就不要写。

==================================================
绝对禁止
==================================================

不要补充你自己的知识。

不要自行添加：

- 数字
- 人名
- 时间
- 公司内部信息
- benchmark
- 实验结果
- 论文信息
- 专家观点
- 技术细节
- 产品参数
- 用户规模
- 市场数据
- 原因
- 后果
- 商业影响
- 行业预测
- 未来计划

特别注意：

不能因为你“知道这个产品”
就自动补充产品功能。

不能因为你“知道这家公司”
就自动补充公司背景。

只能使用输入内容。

==================================================
输出
==================================================

只输出合法 JSON。

例如：

[
  "事实1",
  "事实2",
  "事实3"
]

如果只能确认一条，就只输出一条。

"""

    result = call_ai([
        {
            "role": "system",
            "content": (
                "你是事实核查编辑。"
                "只能提取输入中明确存在的事实。"
            )
        },
        {
            "role": "user",
            "content": prompt
        }
    ])

    facts = extract_json(
        result
    )

    if not isinstance(
        facts,
        list
    ):

        return []

    cleaned = []

    for fact in facts[:5]:

        if not isinstance(
            fact,
            str
        ):

            continue

        fact = clean_text(
            fact
        )

        if fact:

            cleaned.append(
                fact
            )

    return cleaned


# ============================================================
# 第三步：生成完整公众号文章
# ============================================================

def generate_article(
    news,
    facts,
    content_type
):

    summary = truncate_text(
        news["summary"],
        MAX_ARTICLE_SUMMARY_CHARS
    )

    facts_text = "\n".join(
        f"- {fact}"
        for fact in facts
    )

    type_name = CONTENT_TYPES.get(
        content_type,
        "AI内容"
    )

    prompt = f"""
你现在是微信公众号「web前端开发之旅」的主编。

今天确定的文章类型：

{type_name}

请围绕下面这一个核心主题，
写一篇完整的中文微信公众号文章。

注意：

这不是新闻列表。

也不是资料堆砌。

必须是一篇完整、连贯、
有阅读价值的文章。

==================================================
核心信息
==================================================

来源：
{news['source']}

原始标题：
{news['title']}

发布时间：
{news['pub_date']}

RSS摘要：
{summary}

已经确认的事实：

{facts_text}

原文：
{news['link']}

==================================================
最重要的事实规则
==================================================

你只能使用：

1. 原始标题
2. RSS摘要
3. 已确认事实

作为事实依据。

绝对不能从自己的知识库补充事实。

禁止编造：

- 数字
- 人名
- 时间
- 公司内部信息
- benchmark
- 实验数据
- 论文
- 专家观点
- 技术细节
- 产品参数
- 用户规模
- 市场数据
- 原因
- 后果
- 商业影响
- 行业预测
- 未来计划

如果资料没有提供，
就不要写。

==================================================
分析可以写，但必须区分
==================================================

允许加入编辑分析。

例如：

“如果只看这一次变化，真正值得关注的其实是……”

“从开发者的角度来看，这里面有一个很现实的问题……”

“这件事情更值得我们关注的地方，并不是……”

这些属于编辑观点。

但是：

不能把自己的推测写成新闻事实。

不能使用没有资料支撑的：

“业内认为”
“专家表示”
“市场普遍认为”
“这意味着”
“有望”
“预计”
“可能会”

除非这些内容本身明确存在于输入材料中。

==================================================
文章风格
==================================================

公众号：

web前端开发之旅

读者主要是：

- Web前端开发者
- 软件开发者
- AI开发者
- AI工具使用者
- 对AI技术感兴趣的程序员

文章风格：

- 简洁
- 清楚
- 有观点
- 有解释
- 有自然过渡
- 少一点“AI生成感”
- 不要像新闻通讯社
- 不要像论文
- 不要疯狂堆专业术语
- 不要为了凑字数重复内容

可以适当使用：

“其实”
“真正值得注意的是”
“换个角度看”
“对开发者来说”

但不要滥用。

==================================================
不同类型的写法
==================================================

如果是：

【AI新闻】

重点：

发生了什么
→ 关键事实
→ 为什么值得关注
→ 对开发者/AI从业者有什么启发

【AI技术】

重点：

这个技术/变化是什么
→ 输入资料明确说明了什么
→ 为什么值得关注
→ 开发者应该怎么看

不要擅自补充技术原理。

如果原资料没有技术细节，
就不要自己补技术细节。

【AI应用】

重点：

这个AI应用/工具解决什么问题
→ 输入资料明确展示了什么
→ 为什么值得关注
→ 对普通开发者/用户有什么启发

不要自行增加产品功能。

【AI × 前端】

重点：

AI与前端之间发生了什么
→ 明确事实
→ 对开发流程的启发
→ 前端开发者应该关注什么

不要自行编造Vue、React、JavaScript、
浏览器或具体框架的技术细节。

==================================================
文章长度
==================================================

目标：

约1500～2200个中文字符。

但：

宁可内容紧凑，
也不要为了凑字数重复。

==================================================
文章结构
==================================================

必须包含：

title
lead
sections
ending

sections：

必须生成4个章节。

程序最后会固定增加：

05 写在最后

因此你只生成前4章。

==================================================
章节要求
==================================================

每章：

heading
paragraphs
subsections
highlight
list

其中：

subsections 可以为空。

highlight 可以为空。

list 可以为空。

不要为了格式而硬塞内容。

==================================================
章节标题
==================================================

不要使用这种机械标题：

“发生了什么”
“关键细节”
“为什么值得关注”
“对开发者的启发”

应该根据文章主题生成有阅读感的标题。

例如：

“01 AI开始进入真正的开发流程”

“02 真正值得注意的，不只是这个工具”

“03 为什么开发者应该关注这件事”

但不能制造输入中不存在的事实。

每个标题尽量：

20个汉字以内。

==================================================
小标题
==================================================

适合时使用：

“🔹 一个容易被忽视的细节”

“🔹 真正值得关注的地方”

“🧩 从开发者角度怎么看”

不要机械添加。

==================================================
highlight
==================================================

只有真正适合总结时使用。

例如：

“一句话总结：真正值得关注的，不只是这一次变化，而是开发者正在重新理解AI工具的使用方式。”

这是编辑总结。

不能伪造新闻事实。

不适合就：

""

==================================================
list
==================================================

只有适合时使用。

例如：

[
  "第一点",
  "第二点",
  "第三点"
]

不要为了格式硬凑。

==================================================
ending
==================================================

ending 为2～3段。

要自然收束全文。

不要突然做没有事实依据的行业预测。

==================================================
JSON
==================================================

只输出合法JSON。

不要输出Markdown。

不要输出```json。

格式：

{{
  "title": "文章标题",
  "lead": "导语",
  "sections": [
    {{
      "heading": "第一章标题",
      "paragraphs": [
        "第一段",
        "第二段"
      ],
      "subsections": [
        {{
          "heading": "🔹 小标题",
          "paragraph": "正文"
        }}
      ],
      "highlight": "",
      "list": []
    }}
  ],
  "ending": [
    "第一段",
    "第二段"
  ]
}}

==================================================
最终检查
==================================================

输出前自己检查：

1. 是否只使用输入事实？
2. 有没有编造数字？
3. 有没有编造人名？
4. 有没有编造专家观点？
5. 有没有加入输入没有提供的技术细节？
6. 有没有把分析写成事实？
7. 是否是一篇完整文章？
8. 是否只有一个核心主题？
9. 是否存在重复内容？
10. 是否符合「web前端开发之旅」？
11. JSON是否合法？
"""

    result = call_ai([
        {
            "role": "system",
            "content": (
                "你是一名严谨的微信公众号编辑。"
                "输出必须严格遵守JSON格式和事实约束。"
            )
        },
        {
            "role": "user",
            "content": prompt
        }
    ])

    article = extract_json(
        result
    )

    if not isinstance(
        article,
        dict
    ):

        raise ValueError(
            "AI生成的文章不是JSON对象"
        )

    return article


# ============================================================
# 清洗标题
# ============================================================

def clean_title(title):

    title = str(
        title or ""
    ).strip()

    title = re.sub(
        r"\*\*(.*?)\*\*",
        r"\1",
        title
    )

    title = re.sub(
        r"^#+\s*",
        "",
        title
    )

    title = title.strip("`")

    title = re.sub(
        r"\s+",
        " ",
        title
    )

    return title.strip()


# ============================================================
# 清洗文章内容
# ============================================================

def clean_generated_text(text):

    if not text:
        return ""

    text = str(text)

    # Markdown链接 → 只保留文字
    text = re.sub(
        r"\[([^\]]+)\]\([^)]+\)",
        r"\1",
        text
    )

    # 删除裸URL
    text = re.sub(
        r"https?://\S+",
        "",
        text
    )

    # Markdown加粗
    text = re.sub(
        r"\*\*(.*?)\*\*",
        r"\1",
        text
    )

    # Markdown斜体
    text = re.sub(
        r"(?<!\*)\*([^*]+)\*(?!\*)",
        r"\1",
        text
    )

    # Markdown标题
    text = re.sub(
        r"^#{1,6}\s*",
        "",
        text
    )

    text = re.sub(
        r"\n{3,}",
        "\n\n",
        text
    )

    return text.strip()


# ============================================================
# 标准化文章 JSON
# ============================================================

def normalize_article(
    article,
    news,
    content_type
):

    title = clean_title(
        article.get(
            "title",
            ""
        )
    )

    if not title:

        title = clean_title(
            news["title"]
        )

    lead = clean_generated_text(
        article.get(
            "lead",
            ""
        )
    )

    normalized_sections = []

    sections = article.get(
        "sections",
        []
    )

    if not isinstance(
        sections,
        list
    ):

        sections = []

    for section in sections[:4]:

        if not isinstance(
            section,
            dict
        ):

            continue

        heading = clean_generated_text(
            section.get(
                "heading",
                ""
            )
        )

        if not heading:
            continue

        paragraphs = section.get(
            "paragraphs",
            []
        )

        if not isinstance(
            paragraphs,
            list
        ):

            paragraphs = []

        cleaned_paragraphs = []

        for paragraph in paragraphs:

            paragraph = clean_generated_text(
                paragraph
            )

            if paragraph:

                cleaned_paragraphs.append(
                    paragraph
                )

        subsections = section.get(
            "subsections",
            []
        )

        if not isinstance(
            subsections,
            list
        ):

            subsections = []

        cleaned_subsections = []

        for subsection in subsections:

            if not isinstance(
                subsection,
                dict
            ):

                continue

            subheading = clean_generated_text(
                subsection.get(
                    "heading",
                    ""
                )
            )

            paragraph = clean_generated_text(
                subsection.get(
                    "paragraph",
                    ""
                )
            )

            if (
                subheading
                and paragraph
            ):

                cleaned_subsections.append({
                    "heading": subheading,
                    "paragraph": paragraph
                })

        highlight = clean_generated_text(
            section.get(
                "highlight",
                ""
            )
        )

        items = section.get(
            "list",
            []
        )

        if not isinstance(
            items,
            list
        ):

            items = []

        cleaned_list = []

        for item in items:

            item = clean_generated_text(
                item
            )

            if item:

                cleaned_list.append(
                    item
                )

        normalized_sections.append({
            "heading": heading,
            "paragraphs": cleaned_paragraphs,
            "subsections": cleaned_subsections,
            "highlight": highlight,
            "list": cleaned_list
        })

    ending = article.get(
        "ending",
        []
    )

    if not isinstance(
        ending,
        list
    ):

        ending = []

    cleaned_ending = []

    for paragraph in ending:

        paragraph = clean_generated_text(
            paragraph
        )

        if paragraph:

            cleaned_ending.append(
                paragraph
            )

    return {
        "title": title,
        "lead": lead,
        "sections": normalized_sections,
        "ending": cleaned_ending,

        "content_type": content_type,

        "content_type_name":
            CONTENT_TYPES.get(
                content_type,
                "AI内容"
            ),

        "source": news["source"],
        "original_link": news["link"],
        "pub_date": news["pub_date"],
        "news_title": news["title"]
    }


# ============================================================
# 保存 article.json
# ============================================================

def save_article_json(article):

    output_file = "article.json"

    with open(
        output_file,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            article,
            f,
            ensure_ascii=False,
            indent=2
        )

    print("")

    print("=" * 60)

    print(
        "公众号文章已经生成"
    )

    print(
        f"文件：{output_file}"
    )

    print(
        f"标题：{article['title']}"
    )

    print(
        f"内容类型："
        f"{article.get('content_type_name', 'AI内容')}"
    )

    print(
        f"正文结构："
        f"{len(article['sections'])} 个章节"
    )

    print("=" * 60)


# ============================================================
# 主程序
# ============================================================

def main():

    print("")

    print("=" * 70)

    print(
        "        0元 AI 内容公众号自动化 V2"
    )

    print(
        "        AI News / Tech / App / Frontend"
    )

    print(
        "        → WeChat Draft"
    )

    print("=" * 70)

    print("")

    print(
        f"公众号：web前端开发之旅"
    )

    print(
        f"执行日期：{get_beijing_date()}"
    )

    all_news = []

    # ========================================================
    # 1. 抓取 RSS
    # ========================================================

    print("")

    print("=" * 70)

    print(
        "【1/5】开始抓取 AI / 科技信息"
    )

    print("=" * 70)

    for source_name, url in RSS_SOURCES.items():

        news = fetch_rss(
            source_name,
            url
        )

        all_news.extend(
            news
        )

    print("")

    print(
        f"所有 RSS 内容总数："
        f"{len(all_news)}"
    )

    if not all_news:

        raise RuntimeError(
            "没有抓取到任何内容"
        )

    # ========================================================
    # 2. AI 选题
    # ========================================================

    print("")

    print("=" * 70)

    print(
        "【2/5】AI 正在判断今天最值得写的主题"
    )

    print("=" * 70)

    screening_result = ask_ai(
        all_news
    )

    print("")

    print(
        "AI 原始选题结果："
    )

    print(
        screening_result
    )

    ai_result = extract_json(
        screening_result
    )

    selected_result = filter_selected_news(
        ai_result,
        all_news
    )

    if not selected_result:

        raise RuntimeError(
            "AI 没有筛选出符合条件的内容"
        )

    selected_news = selected_result[
        "news"
    ]

    selected_score = selected_result[
        "score"
    ]

    selected_reason = selected_result[
        "reason"
    ]

    selected_content_type = (
        selected_result[
            "content_type"
        ]
    )

    print("")

    print("=" * 70)

    print(
        "最终选中的今日主题"
    )

    print("=" * 70)

    print(
        f"内容类型："
        f"{CONTENT_TYPES.get(selected_content_type)}"
    )

    print(
        f"评分：{selected_score}"
    )

    print(
        f"来源："
        f"{selected_news['source']}"
    )

    print(
        f"标题："
        f"{selected_news['title']}"
    )

    print(
        f"发布时间："
        f"{selected_news['pub_date']}"
    )

    print(
        f"链接："
        f"{selected_news['link']}"
    )

    print(
        f"选题理由："
        f"{selected_reason}"
    )

    # ========================================================
    # 3. 提取事实
    # ========================================================

    print("")

    print("=" * 70)

    print(
        "【3/5】开始提取可靠事实"
    )

    print("=" * 70)

    facts = extract_facts(
        selected_news
    )

    print("")

    print(
        "确认事实："
    )

    for index, fact in enumerate(
        facts,
        start=1
    ):

        print(
            f"{index}. {fact}"
        )

    if not facts:

        print(
            "警告：没有提取到明确事实。"
        )

        print(
            "文章生成将严格依赖标题和RSS摘要。"
        )

    # ========================================================
    # 4. 生成文章
    # ========================================================

    print("")

    print("=" * 70)

    print(
        "【4/5】开始生成完整公众号文章"
    )

    print("=" * 70)

    article_raw = generate_article(
        selected_news,
        facts,
        selected_content_type
    )

    article = normalize_article(
        article_raw,
        selected_news,
        selected_content_type
    )

    # ========================================================
    # 5. 保存
    # ========================================================

    print("")

    print("=" * 70)

    print(
        "【5/5】保存 article.json"
    )

    print("=" * 70)

    save_article_json(
        article
    )

    # ========================================================
    # 文章预览
    # ========================================================

    print("")

    print("=" * 70)

    print(
        "文章预览"
    )

    print("=" * 70)

    print("")

    print(
        "【内容类型】"
    )

    print(
        article.get(
            "content_type_name",
            "AI内容"
        )
    )

    print("")

    print(
        "【标题】"
    )

    print(
        article["title"]
    )

    print("")

    print(
        "【导语】"
    )

    print(
        article["lead"]
    )

    for index, section in enumerate(
        article["sections"],
        start=1
    ):

        print("")

        print(
            f"【{index:02d} "
            f"{section['heading']}】"
        )

        for paragraph in section[
            "paragraphs"
        ]:

            print(
                paragraph
            )

        for subsection in section[
            "subsections"
        ]:

            print("")

            print(
                subsection["heading"]
            )

            print(
                subsection["paragraph"]
            )

        if section[
            "highlight"
        ]:

            print("")

            print(
                "【金句】"
            )

            print(
                section["highlight"]
            )

        if section[
            "list"
        ]:

            print("")

            for item in section[
                "list"
            ]:

                print(
                    f"• {item}"
                )

    print("")

    print(
        "【05 写在最后】"
    )

    for paragraph in article[
        "ending"
    ]:

        print(
            paragraph
        )

    print("")

    print(
        f"来源："
        f"{article['source']}"
    )

    print(
        f"原文："
        f"{article['original_link']}"
    )

    print("")

    print("=" * 70)

    print(
        "AI 内容文章生成完成"
    )

    print("=" * 70)


if __name__ == "__main__":
    main()
