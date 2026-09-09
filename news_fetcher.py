import os
import json
import time
import re
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta


# ============================================================
# 基础配置
# ============================================================

SILICONFLOW_API_KEY = os.environ.get("SILICONFLOW_API_KEY")

AI_API_URL = "https://api.siliconflow.cn/v1/chat/completions"

AI_MODEL = "Qwen/Qwen3-8B"

# SiliconFlow 请求超时时间
AI_TIMEOUT = 120

# 最大重试次数
MAX_RETRIES = 3

# 每次失败后等待
RETRY_WAIT = 5

# RSS 新闻源
RSS_SOURCES = {
    "Ars Technica": "https://feeds.arstechnica.com/arstechnica/technology-lab",
    "MIT Technology Review": "https://www.technologyreview.com/feed/",
}


# ============================================================
# 工具函数
# ============================================================

def clean_text(text):
    """
    清理 HTML、空白字符等。
    """

    if not text:
        return ""

    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)

    return text.strip()


def get_beijing_date():
    """
    获取北京时间日期。
    """

    beijing_tz = timezone(timedelta(hours=8))

    now = datetime.now(beijing_tz)

    return now.strftime("%Y年%m月%d日")


# ============================================================
# RSS 抓取
# ============================================================

def fetch_rss(source_name, rss_url):
    """
    抓取 RSS / Atom。
    """

    print(f"\n正在抓取：{source_name}")
    print(f"RSS：{rss_url}")

    try:

        request = urllib.request.Request(
            rss_url,
            headers={
                "User-Agent": "Mozilla/5.0 AI-News-Bot"
            }
        )

        with urllib.request.urlopen(
            request,
            timeout=30
        ) as response:

            data = response.read()

        root = ET.fromstring(data)

        news_list = []

        # ----------------------------------------------------
        # RSS
        # ----------------------------------------------------

        items = root.findall(".//item")

        if items:

            for item in items:

                title = item.findtext("title", default="")
                summary = item.findtext("description", default="")
                link = item.findtext("link", default="")
                pub_date = item.findtext("pubDate", default="")

                title = clean_text(title)
                summary = clean_text(summary)
                link = clean_text(link)
                pub_date = clean_text(pub_date)

                if not title:
                    continue

                news_list.append({
                    "source": source_name,
                    "title": title,
                    "summary": summary,
                    "link": link,
                    "pub_date": pub_date
                })

        # ----------------------------------------------------
        # Atom
        # ----------------------------------------------------

        if not news_list:

            namespaces = {
                "atom": "http://www.w3.org/2005/Atom"
            }

            entries = root.findall(
                ".//atom:entry",
                namespaces
            )

            for entry in entries:

                title_element = entry.find(
                    "atom:title",
                    namespaces
                )

                summary_element = entry.find(
                    "atom:summary",
                    namespaces
                )

                content_element = entry.find(
                    "atom:content",
                    namespaces
                )

                published_element = entry.find(
                    "atom:published",
                    namespaces
                )

                updated_element = entry.find(
                    "atom:updated",
                    namespaces
                )

                title = ""

                if title_element is not None:
                    title = title_element.text or ""

                summary = ""

                if summary_element is not None:
                    summary = summary_element.text or ""

                if not summary and content_element is not None:
                    summary = content_element.text or ""

                pub_date = ""

                if published_element is not None:
                    pub_date = published_element.text or ""

                if not pub_date and updated_element is not None:
                    pub_date = updated_element.text or ""

                link = ""

                link_element = entry.find(
                    "atom:link",
                    namespaces
                )

                if link_element is not None:
                    link = link_element.attrib.get(
                        "href",
                        ""
                    )

                title = clean_text(title)
                summary = clean_text(summary)
                link = clean_text(link)
                pub_date = clean_text(pub_date)

                if not title:
                    continue

                news_list.append({
                    "source": source_name,
                    "title": title,
                    "summary": summary,
                    "link": link,
                    "pub_date": pub_date
                })

        print(
            f"{source_name} 抓取到 "
            f"{len(news_list)} 条新闻"
        )

        return news_list

    except Exception as e:

        print(
            f"{source_name} RSS 抓取失败：{e}"
        )

        return []


# ============================================================
# SiliconFlow AI
# ============================================================

def call_ai(prompt, max_tokens=1800):
    """
    调用 SiliconFlow。

    保留：
    - 120 秒超时
    - 最多重试 3 次
    - 每次失败等待 5 秒
    """

    if not SILICONFLOW_API_KEY:

        raise RuntimeError(
            "没有找到 SILICONFLOW_API_KEY"
        )

    payload = {
        "model": AI_MODEL,

        "messages": [
            {
                "role": "user",
                "content": prompt
            }
        ],

        "temperature": 0.2,

        "max_tokens": max_tokens
    }

    data = json.dumps(
        payload,
        ensure_ascii=False
    ).encode("utf-8")

    request = urllib.request.Request(
        AI_API_URL,
        data=data,
        headers={
            "Content-Type": "application/json",
            "Authorization":
                f"Bearer {SILICONFLOW_API_KEY}"
        },
        method="POST"
    )

    last_error = None

    for attempt in range(1, MAX_RETRIES + 1):

        print(
            f"\n正在调用 SiliconFlow，"
            f"第 {attempt}/{MAX_RETRIES} 次..."
        )

        try:

            with urllib.request.urlopen(
                request,
                timeout=AI_TIMEOUT
            ) as response:

                result = json.loads(
                    response.read().decode("utf-8")
                )

            content = (
                result["choices"][0]
                ["message"]["content"]
            )

            print("SiliconFlow 调用成功")

            return content

        except Exception as e:

            last_error = e

            print(
                f"SiliconFlow 调用失败：{e}"
            )

            if attempt < MAX_RETRIES:

                print(
                    f"{RETRY_WAIT} 秒后自动重试..."
                )

                time.sleep(RETRY_WAIT)

    raise RuntimeError(
        f"SiliconFlow 连续 {MAX_RETRIES} 次调用失败："
        f"{last_error}"
    )


# ============================================================
# 构建新闻资料
# ============================================================

def build_news_context(all_news):
    """
    把 RSS 新闻整理成 AI 可以读取的资料。
    """

    blocks = []

    for index, news in enumerate(
        all_news,
        start=1
    ):

        block = f"""
【新闻 {index}】

来源：{news.get("source", "")}

标题：
{news.get("title", "")}

摘要：
{news.get("summary", "")}

发布时间：
{news.get("pub_date", "")}

原文链接：
{news.get("link", "")}
"""

        blocks.append(block)

    return "\n".join(blocks)


# ============================================================
# AI 初步筛选
# ============================================================

def ask_ai(all_news):

    print(
        "\n========== 开始 AI 新闻筛选 =========="
    )

    news_context = build_news_context(
        all_news
    )

    prompt = f"""
你是一名非常严格的 AI 科技新闻编辑。

现在需要从下面的新闻资料中筛选真正值得发布到
“AI 新闻公众号”的新闻。

新闻资料：

{news_context}


==============================
筛选标准
==============================

一、必须是真正的 AI 核心新闻

只有满足以下条件才能 is_ai=true：

AI、人工智能、AI Agent、大模型、机器学习、
生成式 AI、AI 安全、AI 研究、AI 芯片等必须是
新闻的核心主题。

请使用一个非常重要的判断：

“如果把 AI 相关内容从这篇新闻中删除，
这篇新闻本身是否仍然成立？”

如果答案是“是”，而 AI 只是顺带出现，
则必须：

is_ai=false


二、严格排除：

- 普通网络安全新闻
- 普通软件新闻
- 普通云计算新闻
- 普通硬件新闻
- 普通机器人新闻
- 普通企业新闻
- 普通商业新闻
- 普通能源新闻
- 普通科学新闻
- 普通汽车新闻
- 普通芯片新闻

除非 AI 本身就是核心。


三、严格排除综合型文章

以下类型原则上不要选择：

- The Download
- Newsletter
- weekly roundup
- daily roundup
- and more
- 科技简报
- 本周还有……
- 今日还有……
- 一个标题同时讨论多个完全不同领域

如果一篇文章只是一个综合新闻简报，
即使其中包含 AI 新闻，也：

is_ai=false


四、重大程度

is_major=true 必须意味着：

- 重要 AI 产品/模型发布
- 重要 AI 研究突破
- 重要 AI 公司重大事件
- 重大 AI 安全事件
- AI 行业重大政策
- AI Agent 重大进展
- 对 AI 行业有明显影响的事件

普通的小更新不要选择。


五、重复新闻

如果多篇新闻报道的是同一个事件：

duplicate_group 必须尽量保持一致。

例如：

openai-sandbox-security

而不是人为拆成：

openai-sandbox-escape
openai-rogue-agents


六、不要凑数量

宁可只返回 1～3 条真正重要的 AI 新闻，
也不要为了凑够 5 条而选择质量较差的新闻。


七、事实限制

你只能根据提供的：

标题
摘要
来源
发布时间
原文链接

判断新闻。

不要使用你自己的知识补充新闻事实。


==============================
输出格式
==============================

只输出 JSON 数组。

不要输出 Markdown。

不要输出解释。

格式：

[
  {{
    "index": 1,
    "is_ai": true,
    "is_major": true,
    "duplicate_group": "xxx",
    "score": 9,
    "reason": "简短说明为什么这是 AI 核心新闻"
  }}
]

score 范围：

1～10。

只有 score >= 7 的新闻才应该返回。

再次强调：

宁可少选，不要凑数。
"""

    result = call_ai(
        prompt,
        max_tokens=1800
    )

    print(
        "\n========== AI 原始筛选结果 =========="
    )

    print(result)

    # --------------------------------------------------------
    # 清理 Markdown JSON
    # --------------------------------------------------------

    result = result.strip()

    if result.startswith("```"):

        result = re.sub(
            r"^```(?:json)?",
            "",
            result,
            flags=re.IGNORECASE
        )

        result = re.sub(
            r"```$",
            "",
            result
        )

        result = result.strip()

    try:

        selected_news = json.loads(
            result
        )

        if not isinstance(
            selected_news,
            list
        ):

            raise ValueError(
                "AI 返回结果不是数组"
            )

        return selected_news

    except Exception as e:

        print(
            f"AI JSON 解析失败：{e}"
        )

        print(
            "原始 AI 返回："
        )

        print(result)

        return []


# ============================================================
# 程序二次过滤
# ============================================================

def filter_selected_news(
    selected_news,
    all_news
):

    print(
        "\n========== 程序二次过滤 =========="
    )

    valid_news = []

    # --------------------------------------------------------
    # 第一层：AI 判断字段
    # --------------------------------------------------------

    for item in selected_news:

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
            or index > len(all_news)
        ):

            print(
                f"过滤：新闻 {index}，index 无效"
            )

            continue

        is_ai = item.get(
            "is_ai",
            False
        )

        is_major = item.get(
            "is_major",
            False
        )

        try:

            score = int(
                item.get(
                    "score",
                    0
                )
            )

        except Exception:

            score = 0

        if is_ai is not True:

            print(
                f"过滤：新闻 {index}，"
                f"is_ai={is_ai}"
            )

            continue

        if is_major is not True:

            print(
                f"过滤：新闻 {index}，"
                f"is_major={is_major}"
            )

            continue

        if score < 7:

            print(
                f"过滤：新闻 {index}，"
                f"score={score}"
            )

            continue

        news = all_news[index - 1]

        title = news.get(
            "title",
            ""
        ).lower()

        # ----------------------------------------------------
        # 第二层：程序识别综合型文章
        # ----------------------------------------------------

        roundup_keywords = [
            "the download",
            "newsletter",
            "weekly roundup",
            "daily roundup",
            "roundup:",
            "and more",
            "this week in",
            "today in tech",
        ]

        is_roundup = any(
            keyword in title
            for keyword in roundup_keywords
        )

        if is_roundup:

            print(
                f"过滤：新闻 {index}，"
                f"疑似综合型文章："
                f"{news.get('title', '')}"
            )

            continue

        valid_news.append(item)

    # --------------------------------------------------------
    # 按分数排序
    # --------------------------------------------------------

    valid_news.sort(
        key=lambda x: int(
            x.get(
                "score",
                0
            )
        ),
        reverse=True
    )

    # --------------------------------------------------------
    # 第三层：duplicate_group 去重
    # --------------------------------------------------------

    unique_news = []

    duplicate_groups = set()

    for item in valid_news:

        group = str(
            item.get(
                "duplicate_group",
                ""
            )
        ).strip().lower()

        if not group:

            group = (
                f"news-{item['index']}"
            )

        if group in duplicate_groups:

            print(
                f"过滤：新闻 "
                f"{item['index']}，"
                f"属于重复事件："
                f"{group}"
            )

            continue

        duplicate_groups.add(
            group
        )

        unique_news.append(
            item
        )

    # --------------------------------------------------------
    # 第四层：简单标题相似度去重
    # --------------------------------------------------------

    final_news = []

    title_keywords_groups = []

    for item in unique_news:

        index = int(
            item["index"]
        )

        title = all_news[
            index - 1
        ].get(
            "title",
            ""
        ).lower()

        # 提取一些明显的核心实体
        keywords = set()

        important_words = [
            "openai",
            "anthropic",
            "google",
            "microsoft",
            "meta",
            "nvidia",
            "deepseek",
            "qwen",
            "gemini",
            "chatgpt",
            "agent",
            "agents",
            "sandbox",
            "math",
            "mathematics",
            "ai",
        ]

        for word in important_words:

            if word in title:

                keywords.add(word)

        is_similar = False

        for old_keywords in title_keywords_groups:

            common = (
                keywords
                & old_keywords
            )

            # 两个标题共享至少两个核心词，
            # 且核心词明显相同，
            # 认为可能属于同一事件。
            if len(common) >= 2:

                print(
                    f"过滤：新闻 {index}，"
                    f"疑似与已有新闻重复："
                    f"{common}"
                )

                is_similar = True

                break

        if is_similar:

            continue

        title_keywords_groups.append(
            keywords
        )

        final_news.append(
            item
        )

    # 最多 5 条
    final_news = final_news[:5]

    print(
        f"\n最终保留 "
        f"{len(final_news)} 条新闻"
    )

    for item in final_news:

        index = int(
            item["index"]
        )

        print(
            f"- 新闻 {index} | "
            f"score={item.get('score')} | "
            f"{all_news[index - 1]['title']}"
        )

    return final_news


# ============================================================
# 生成公众号文章
# ============================================================

def generate_article(
    selected_news,
    all_news
):

    print(
        "\n========== 开始生成公众号文章 =========="
    )

    article_news = []

    for item in selected_news:

        index = int(
            item["index"]
        )

        news = all_news[
            index - 1
        ]

        article_news.append({
            "index": index,
            "source": news.get(
                "source",
                ""
            ),
            "title": news.get(
                "title",
                ""
            ),
            "summary": news.get(
                "summary",
                ""
            ),
            "pub_date": news.get(
                "pub_date",
                ""
            )
        })

    news_context = json.dumps(
        article_news,
        ensure_ascii=False,
        indent=2
    )

    beijing_date = get_beijing_date()

    prompt = f"""
你是一名中文科技公众号编辑。

今天是 {beijing_date}。

请根据下面提供的新闻资料，
写一篇适合微信公众号发布的中文 AI 新闻文章。


==============================
最重要的原则：禁止编造事实
==============================

你只能使用下面资料中明确出现的信息：

- 新闻标题
- 新闻摘要
- 来源
- 发布时间

严禁使用你自己的知识补充事实。

特别禁止：

- 自己补充数字
- 自己补充人物观点
- 自己补充专家观点
- 自己补充“业内人士表示”
- 自己补充“学术界认为”
- 自己补充公司内部信息
- 自己补充没有出现在资料里的技术细节
- 自己猜测事件原因
- 自己猜测事件后果
- 自己虚构采访
- 自己虚构数据


如果资料没有明确说明：

“为什么值得关注”

就不要强行分析。

可以使用非常克制的总结，
但必须明显属于基于资料的概括。


==============================
新闻资料
==============================

{news_context}


==============================
文章要求
==============================

1. 使用自然的中文。

2. 不要有明显的 AI 腔。

避免大量使用：

“这意味着”
“值得注意的是”
“重新定义”
“正在改变”
“引发行业深思”
“未来可期”
“具有里程碑意义”

除非资料本身确实支持。


3. 不要写夸张标题。

4. 不要虚构新闻。

5. 每条新闻控制在 2～4 个自然段。

6. 每条新闻按照：

【新闻1】
标题

发生了什么？

用资料中的事实进行简洁说明。

为什么值得关注？

如果资料不足，就简单写：
“目前从公开资料来看，这一事件主要体现了……”
但不要补充资料之外的事实。


7. 文章开头简短。

8. 文章结尾写一个非常简短的总结。

9. 不要输出 URL。

10. 不要输出“来源”。

11. 不要输出 Markdown 链接。

因为来源和 URL 将由程序自动添加。


==============================
输出格式
==============================

直接输出正文。

不要输出：

```markdown
