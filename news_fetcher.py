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


# ============================================================
# RSS 新闻源
# ============================================================

RSS_SOURCES = {
    "Ars Technica": "https://feeds.arstechnica.com/arstechnica/technology-lab",
    "MIT Technology Review": "https://www.technologyreview.com/feed/",
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
    return datetime.now(beijing_tz).strftime("%Y-%m-%d")


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

        print(f"{source_name} RSS 获取成功：{len(data)} bytes")

    except Exception as e:
        print(f"{source_name} RSS 获取失败：{e}")
        return []

    try:
        root = ET.fromstring(data)
    except Exception as e:
        print(f"{source_name} RSS XML 解析失败：{e}")
        return []

    news_list = []

    # --------------------------------------------------------
    # RSS 2.0
    # --------------------------------------------------------

    items = root.findall(".//item")

    for item in items[:MAX_NEWS_PER_SOURCE]:

        title = item.findtext("title", "")
        summary = item.findtext("description", "")
        link = item.findtext("link", "")
        pub_date = item.findtext("pubDate", "")

        title = clean_text(title)
        summary = clean_text(summary)
        link = clean_text(link)
        pub_date = clean_text(pub_date)

        if not title or not link:
            continue

        news_list.append({
            "source": source_name,
            "title": title,
            "summary": truncate_text(summary, MAX_FACT_SUMMARY_CHARS),
            "link": link,
            "pub_date": pub_date,
        })

    # --------------------------------------------------------
    # Atom
    # --------------------------------------------------------

    if not news_list:

        atom_entries = root.findall(
            ".//{http://www.w3.org/2005/Atom}entry"
        )

        for entry in atom_entries[:MAX_NEWS_PER_SOURCE]:

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
                href = link_node.attrib.get("href", "")
                rel = link_node.attrib.get("rel", "")

                if href and (not rel or rel == "alternate"):
                    link = href
                    break

            title = clean_text(
                title_node.text if title_node is not None else ""
            )

            summary = clean_text(
                summary_node.text
                if summary_node is not None
                else ""
            )

            pub_date = ""

            if published_node is not None:
                pub_date = clean_text(published_node.text)

            if not pub_date and updated_node is not None:
                pub_date = clean_text(updated_node.text)

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

    print(f"{source_name} 共抓取 {len(news_list)} 条新闻")

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

    for attempt in range(1, MAX_RETRIES + 1):

        print("")
        print(
            f"正在调用 SiliconFlow，"
            f"第 {attempt}/{MAX_RETRIES} 次..."
        )

        request = urllib.request.Request(
            SILICONFLOW_URL,
            data=body,
            headers={
                "Authorization": f"Bearer {SILICONFLOW_API_KEY}",
                "Content-Type": "application/json",
                "User-Agent": "AI-News-WeChat/1.0"
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
                response_data.decode("utf-8")
            )

            if "error" in result:
                raise RuntimeError(
                    f"SiliconFlow API 返回错误：{result['error']}"
                )

            choices = result.get("choices", [])

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

            print("SiliconFlow 调用成功")

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
                f"SiliconFlow HTTP 错误："
                f"{e.code} {error_body}"
            )

            if not is_retryable_http_status(e.code):
                raise RuntimeError(
                    f"SiliconFlow 请求失败：HTTP {e.code} "
                    f"{error_body}"
                )

        except (
            urllib.error.URLError,
            TimeoutError,
            socket.timeout
        ) as e:

            last_error = e

            print(
                f"SiliconFlow 请求超时或网络错误：{e}"
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

            time.sleep(RETRY_WAIT_SECONDS)

    raise RuntimeError(
        f"SiliconFlow 连续 {MAX_RETRIES} 次请求失败："
        f"{last_error}"
    )


# ============================================================
# 构造新闻上下文
# ============================================================

def build_news_context(news_list, summary_limit):
    blocks = []

    for index, news in enumerate(news_list, start=1):

        block = (
            f"新闻编号：{index}\n"
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
# 第一步：AI 筛选新闻
# ============================================================

def ask_ai(news_list):

    context = build_news_context(
        news_list,
        MAX_SCREENING_SUMMARY_CHARS
    )

    prompt = f"""
你是一名严格的 AI 新闻编辑。

下面是今天从 RSS 抓取到的新闻。

你的任务是：
从这些新闻中找出真正值得写成微信公众号文章的、
最重要的一条 AI 核心新闻。

【非常重要】
你只能根据下面提供的：
- 新闻标题
- RSS摘要
- 来源
- 发布时间
- 原文链接

进行判断。

绝对不能根据你自己的知识补充新闻事实。

筛选要求：

1. 必须是 AI 核心新闻。
2. 必须具有较高新闻价值。
3. 优先选择重大模型、AI产品、AI安全、AI研究、
   AI公司重大动作等新闻。
4. 排除普通科技新闻。
5. 排除新闻汇总、newsletter、roundup。
6. 如果同一事件出现多篇报道，归为同一个
   duplicate_group。
7. score 使用 0-10 分。
8. 最多返回5个候选。
9. 最终程序会选择其中优先级最高的一条。

请严格输出 JSON，不要输出任何解释：

[
  {{
    "index": 1,
    "is_ai": true,
    "is_major": true,
    "score": 9,
    "duplicate_group": "事件名称",
    "reason": "只能根据RSS提供的信息简短说明"
  }}
]

新闻：

{context}
"""

    result = call_ai([
        {
            "role": "system",
            "content": (
                "你是一个严谨的AI新闻筛选器。"
                "只使用输入信息，不允许补充外部事实。"
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

    # 去除 Markdown JSON 代码块
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
        candidate = text[start:end + 1]

        try:
            return json.loads(candidate)
        except Exception:
            pass

    # 再寻找对象
    start = text.find("{")
    end = text.rfind("}")

    if start != -1 and end != -1:
        candidate = text[start:end + 1]

        try:
            return json.loads(candidate)
        except Exception:
            pass

    raise ValueError(
        f"AI 返回内容无法解析为 JSON：\n{text}"
    )


# ============================================================
# 程序二次过滤
# ============================================================

def filter_selected_news(
    ai_result,
    news_list
):

    if isinstance(ai_result, dict):
        candidates = ai_result.get(
            "candidates",
            []
        )
    else:
        candidates = ai_result

    valid = []

    used_duplicate_groups = set()

    for item in candidates:

        if not isinstance(item, dict):
            continue

        try:
            index = int(item.get("index", 0))
        except Exception:
            continue

        if index < 1 or index > len(news_list):
            continue

        if item.get("is_ai") is not True:
            continue

        if item.get("is_major") is not True:
            continue

        try:
            score = float(item.get("score", 0))
        except Exception:
            score = 0

        if score < 7:
            continue

        duplicate_group = str(
            item.get("duplicate_group", "")
        ).strip()

        if duplicate_group:
            if duplicate_group in used_duplicate_groups:
                continue

            used_duplicate_groups.add(
                duplicate_group
            )

        title = news_list[index - 1]["title"].lower()

        roundup_keywords = [
            "roundup",
            "newsletter",
            "weekly",
            "this week",
            "daily roundup",
            "news roundup"
        ]

        if any(
            keyword in title
            for keyword in roundup_keywords
        ):
            continue

        valid.append({
            "news": news_list[index - 1],
            "score": score,
            "reason": str(
                item.get("reason", "")
            ).strip()
        })

    if not valid:
        return None

    valid.sort(
        key=lambda x: x["score"],
        reverse=True
    )

    return valid[0]["news"]


# ============================================================
# 第二步：提取事实
# ============================================================

def extract_facts(news):

    summary = truncate_text(
        news["summary"],
        MAX_FACT_SUMMARY_CHARS
    )

    prompt = f"""
你现在负责给一篇微信公众号文章提取事实依据。

只能使用下面这条 RSS 新闻提供的信息：

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

请最多提取3条明确事实。

【绝对禁止】
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
- 原因
- 后果
- 市场影响
- 用户规模
- 产品能力
- 未来预测

如果RSS摘要没有明确说，就不要写。

只输出 JSON：

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

    facts = extract_json(result)

    if not isinstance(facts, list):
        return []

    cleaned = []

    for fact in facts[:3]:

        if not isinstance(fact, str):
            continue

        fact = clean_text(fact)

        if fact:
            cleaned.append(fact)

    return cleaned


# ============================================================
# 第三步：生成公众号文章结构
# ============================================================

def generate_article(news, facts):

    summary = truncate_text(
        news["summary"],
        MAX_ARTICLE_SUMMARY_CHARS
    )

    facts_text = "\n".join(
        f"- {fact}"
        for fact in facts
    )

    prompt = f"""
你现在是微信公众号「web前端漫游记」的主编。

请围绕下面这一条 AI 新闻，
写一篇完整的中文微信公众号文章。

【新闻信息】

来源：
{news['source']}

标题：
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

1. 新闻标题
2. RSS摘要
3. 上面已经确认的事实

作为新闻事实依据。

绝对不能从自己的知识库补充新闻事实。

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

尤其不要出现：

“据报道”
“业内认为”
“这意味着”
“有望”
“预计”
“可能将”
“业内人士表示”

除非这些内容本身明确存在于输入材料中。

如果资料不足，就宁可不写。

==================================================
文章风格
==================================================

文章不是新闻摘要，也不是新闻列表。

要写成一篇完整、连贯、有阅读价值的微信公众号文章。

整体风格参考：

- 简洁
- 有观点
- 有解释
- 有自然过渡
- 不要“AI味”
- 不要故意堆砌专业术语
- 不要像新闻通讯社
- 不要写成论文
- 不要为了凑字数重复新闻

允许进行“编辑分析”。

但编辑分析必须明显属于分析，
不能伪装成新闻事实。

例如：

“从这个动作本身来看，我们更应该关注的是……”
“如果只看这一次事件，真正值得注意的其实是……”

这种属于编辑观点，可以使用。

==================================================
文章长度
==================================================

目标约1500～2200个中文字符。

不要为了达到字数而重复。

==================================================
固定文章结构
==================================================

必须包含：

title
lead
sections
ending

sections 固定4个。

第1章：解释这件事到底发生了什么。

第2章：围绕新闻中明确存在的关键信息继续展开。

第3章：解释为什么值得关注。
这里可以加入编辑分析，但不能编造事实。

第4章：结合「web前端漫游记」读者群，
讨论对开发者、AI从业者或行业的启发。
只有确实适合时才写。

第5章由程序固定生成：
“写在最后”。

因此 AI 只需要生成前4章。

==================================================
章节标题
==================================================

不要使用：

“发生了什么”
“关键细节”
“为什么值得关注”
“对开发者的启发”

这种机械标题。

应该根据当天新闻动态生成有阅读感的标题。

例如：

“01 一场测试，暴露出AI Agent的新问题”

“02 真正值得注意的，不只是测试结果”

但不要编造新闻没有提供的信息。

每个标题尽量控制在20个汉字以内。

==================================================
每个章节
==================================================

每个 section 包含：

heading
paragraphs
subsections
highlight
list

其中：

subsections 可以为空。

list 可以为空。

highlight 可以为空。

不要为了格式而强行添加。

==================================================
小标题
==================================================

适合时使用。

例如：

“🔹 一个容易被忽视的细节”

“🔹 为什么这个变化值得关注”

“🧩 从开发者角度怎么看”

但不要机械添加。

==================================================
金句
==================================================

highlight 只有真正适合总结时才使用。

例如：

“一句话总结：真正值得关注的，不只是这一次测试，而是AI系统开始暴露出新的安全边界。”

注意：

这是编辑总结，不得伪造新闻事实。

==================================================
列表
==================================================

只有适合时才使用。

例如：

[
  "第一点",
  "第二点",
  "第三点"
]

不要为了格式硬凑列表。

==================================================
结尾
==================================================

ending 为2～3段。

最后应该自然收束全文。

不要突然提出没有事实依据的预测。

==================================================
JSON要求
==================================================

只输出合法 JSON。

不要输出 Markdown。

不要输出 ```json。

格式必须严格类似：

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
8. 是否只有一个核心新闻？
9. 是否存在重复内容？
10. JSON 是否合法？
"""

    result = call_ai([
        {
            "role": "system",
            "content": (
                "你是一名严谨的微信公众号编辑。"
                "输出必须严格遵守 JSON 格式和事实约束。"
            )
        },
        {
            "role": "user",
            "content": prompt
        }
    ])

    article = extract_json(result)

    if not isinstance(article, dict):
        raise ValueError(
            "AI生成的文章不是 JSON 对象"
        )

    return article


# ============================================================
# 清洗标题
# ============================================================

def clean_title(title):

    title = str(title or "").strip()

    # 去掉 Markdown 加粗
    title = re.sub(r"\*\*(.*?)\*\*", r"\1", title)

    # 去掉 Markdown 标题
    title = re.sub(r"^#+\s*", "", title)

    # 去掉多余引号
    title = title.strip("`")

    # 压缩空格
    title = re.sub(r"\s+", " ", title)

    return title.strip()


# ============================================================
# 清洗文章内容
# ============================================================

def clean_generated_text(text):

    if not text:
        return ""

    text = str(text)

    # Markdown 链接 → 只保留文字
    text = re.sub(
        r"\[([^\]]+)\]\([^)]+\)",
        r"\1",
        text
    )

    # 删除裸 URL
    text = re.sub(
        r"https?://\S+",
        "",
        text
    )

    # Markdown 加粗
    text = re.sub(
        r"\*\*(.*?)\*\*",
        r"\1",
        text
    )

    # Markdown 斜体
    text = re.sub(
        r"(?<!\*)\*([^*]+)\*(?!\*)",
        r"\1",
        text
    )

    # Markdown 标题
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

def normalize_article(article, news):

    title = clean_title(
        article.get("title", "")
    )

    if not title:
        title = clean_title(
            news["title"]
        )

    lead = clean_generated_text(
        article.get("lead", "")
    )

    normalized_sections = []

    sections = article.get(
        "sections",
        []
    )

    if not isinstance(sections, list):
        sections = []

    for section in sections[:4]:

        if not isinstance(section, dict):
            continue

        heading = clean_generated_text(
            section.get("heading", "")
        )

        if not heading:
            continue

        paragraphs = section.get(
            "paragraphs",
            []
        )

        if not isinstance(paragraphs, list):
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

            if subheading and paragraph:

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

        if not isinstance(items, list):
            items = []

        cleaned_list = []

        for item in items:

            item = clean_generated_text(
                item
            )

            if item:
                cleaned_list.append(item)

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

    if not isinstance(ending, list):
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
    print("公众号文章已经生成")
    print(f"文件：{output_file}")
    print(f"标题：{article['title']}")
    print(f"正文结构：{len(article['sections'])} 个章节")
    print("=" * 60)


# ============================================================
# 主程序
# ============================================================

def main():

    print("")
    print("=" * 70)
    print("        0元 AI 新闻公众号自动化")
    print("        AI News → WeChat Draft")
    print("=" * 70)

    all_news = []

    # --------------------------------------------------------
    # 1. 抓取 RSS
    # --------------------------------------------------------

    for source_name, url in RSS_SOURCES.items():

        news = fetch_rss(
            source_name,
            url
        )

        all_news.extend(news)

    print("")
    print(f"所有 RSS 新闻总数：{len(all_news)}")

    if not all_news:
        raise RuntimeError(
            "没有抓取到任何新闻"
        )

    # --------------------------------------------------------
    # 2. AI 筛选
    # --------------------------------------------------------

    print("")
    print("=" * 70)
    print("开始使用 AI 筛选核心新闻")
    print("=" * 70)

    screening_result = ask_ai(
        all_news
    )

    print("")
    print("AI 原始筛选结果：")
    print(screening_result)

    ai_result = extract_json(
        screening_result
    )

    selected_news = filter_selected_news(
        ai_result,
        all_news
    )

    if not selected_news:
        raise RuntimeError(
            "AI 没有筛选出符合条件的核心 AI 新闻"
        )

    print("")
    print("=" * 70)
    print("最终选中的核心新闻")
    print("=" * 70)

    print(
        f"来源：{selected_news['source']}"
    )

    print(
        f"标题：{selected_news['title']}"
    )

    print(
        f"链接：{selected_news['link']}"
    )

    # --------------------------------------------------------
    # 3. 提取事实
    # --------------------------------------------------------

    print("")
    print("=" * 70)
    print("开始提取事实")
    print("=" * 70)

    facts = extract_facts(
        selected_news
    )

    print("")
    print("确认事实：")

    for index, fact in enumerate(
        facts,
        start=1
    ):
        print(
            f"{index}. {fact}"
        )

    if not facts:
        print(
            "警告：没有提取到明确事实，"
            "文章生成将严格依赖标题和RSS摘要。"
        )

    # --------------------------------------------------------
    # 4. 生成文章
    # --------------------------------------------------------

    print("")
    print("=" * 70)
    print("开始生成微信公众号文章")
    print("=" * 70)

    article_raw = generate_article(
        selected_news,
        facts
    )

    article = normalize_article(
        article_raw,
        selected_news
    )

    # --------------------------------------------------------
    # 5. 保存
    # --------------------------------------------------------

    save_article_json(
        article
    )

    # --------------------------------------------------------
    # 6. 输出预览
    # --------------------------------------------------------

    print("")
    print("=" * 70)
    print("文章预览")
    print("=" * 70)

    print("")
    print(f"【标题】")
    print(article["title"])

    print("")
    print("【导语】")
    print(article["lead"])

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
            print(paragraph)

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

        if section["highlight"]:
            print("")
            print(
                f"【金句】"
            )
            print(
                section["highlight"]
            )

        if section["list"]:
            print("")
            for item in section["list"]:
                print(
                    f"• {item}"
                )

    print("")
    print("【05 写在最后】")

    for paragraph in article[
        "ending"
    ]:
        print(paragraph)

    print("")
    print(
        f"来源：{article['source']}"
    )

    print(
        f"原文：{article['original_link']}"
    )

    print("")
    print("=" * 70)
    print("AI 新闻文章生成完成")
    print("=" * 70)


if __name__ == "__main__":
    main()
