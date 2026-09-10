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

# 保持之前已经验证过的配置
REQUEST_TIMEOUT = 120
MAX_RETRIES = 3
RETRY_WAIT_SECONDS = 5

# RSS 新闻最多抓取数量
MAX_NEWS_PER_SOURCE = 20

# RSS 摘要发送给 AI 时的最大长度
# 防止一次请求 Prompt 过大
MAX_SCREENING_SUMMARY_CHARS = 800
MAX_FACT_SUMMARY_CHARS = 2000
MAX_ARTICLE_SUMMARY_CHARS = 2500

# 第一次 AI 筛选允许发送给模型的最大上下文长度
MAX_SCREENING_CONTEXT_CHARS = 30000


RSS_SOURCES = {
    "Ars Technica": "https://feeds.arstechnica.com/arstechnica/technology-lab",
    "MIT Technology Review": "https://www.technologyreview.com/feed/",
}


# ============================================================
# 文本清洗
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
    """
    限制文本长度，避免 RSS 摘要过长导致 AI 请求过大。
    """
    if not text:
        return ""

    text = str(text).strip()

    if len(text) <= max_chars:
        return text

    return text[:max_chars].rstrip() + "……[摘要已截断]"


# ============================================================
# 获取北京时间
# ============================================================

def get_beijing_date():
    beijing_tz = timezone(timedelta(hours=8))
    now = datetime.now(beijing_tz)

    return now.strftime("%Y年%m月%d日")


# ============================================================
# RSS 抓取
# ============================================================

def fetch_rss(source_name, rss_url):

    print(f"\n========== 抓取 {source_name} ==========")
    print(rss_url)

    request = urllib.request.Request(
        rss_url,
        headers={
            "User-Agent": "Mozilla/5.0 AI-News-Automation"
        }
    )

    try:

        # RSS 超时也统一使用 120 秒
        with urllib.request.urlopen(
            request,
            timeout=REQUEST_TIMEOUT
        ) as response:

            xml_data = response.read()

        root = ET.fromstring(xml_data)

    except Exception as e:

        print(f"RSS 抓取失败：{e}")

        return []

    news_list = []

    # --------------------------------------------------------
    # RSS <item>
    # --------------------------------------------------------

    items = root.findall(".//item")

    if items:

        for item in items[:MAX_NEWS_PER_SOURCE]:

            title = item.findtext("title", "")
            description = item.findtext("description", "")
            link = item.findtext("link", "")
            pub_date = item.findtext("pubDate", "")

            title = clean_text(title)
            description = clean_text(description)
            link = clean_text(link)
            pub_date = clean_text(pub_date)

            if not title:
                continue

            news_list.append({
                "source": source_name,
                "title": title,
                "summary": description,
                "link": link,
                "pub_date": pub_date
            })

    # --------------------------------------------------------
    # Atom <entry>
    # --------------------------------------------------------

    if not items:

        entries = root.findall(
            ".//{http://www.w3.org/2005/Atom}entry"
        )

        for entry in entries[:MAX_NEWS_PER_SOURCE]:

            title_node = entry.find(
                "{http://www.w3.org/2005/Atom}title"
            )

            summary_node = entry.find(
                "{http://www.w3.org/2005/Atom}summary"
            )

            content_node = entry.find(
                "{http://www.w3.org/2005/Atom}content"
            )

            published_node = entry.find(
                "{http://www.w3.org/2005/Atom}published"
            )

            updated_node = entry.find(
                "{http://www.w3.org/2005/Atom}updated"
            )

            title = ""
            summary = ""
            link = ""
            pub_date = ""

            if title_node is not None:
                title = clean_text(
                    title_node.text or ""
                )

            if summary_node is not None:
                summary = clean_text(
                    summary_node.text or ""
                )

            if not summary and content_node is not None:
                summary = clean_text(
                    content_node.text or ""
                )

            if published_node is not None:
                pub_date = clean_text(
                    published_node.text or ""
                )

            elif updated_node is not None:
                pub_date = clean_text(
                    updated_node.text or ""
                )

            link_nodes = entry.findall(
                "{http://www.w3.org/2005/Atom}link"
            )

            for link_node in link_nodes:

                href = link_node.attrib.get(
                    "href",
                    ""
                )

                if href:

                    link = href

                    break

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
        f"抓取到 {len(news_list)} 条新闻"
    )

    return news_list


# ============================================================
# SiliconFlow HTTP 错误判断
# ============================================================

def is_retryable_http_status(status_code):

    return status_code in {
        429,  # Too Many Requests
        500,  # Internal Server Error
        502,  # Bad Gateway
        503,  # Service Unavailable
        504   # Gateway Timeout
    }


# ============================================================
# SiliconFlow AI 调用
# ============================================================

def call_ai(prompt, max_tokens=1800):

    if not SILICONFLOW_API_KEY:

        raise RuntimeError(
            "没有找到 SILICONFLOW_API_KEY，请检查 GitHub Secrets。"
        )

    payload = {
        "model": MODEL,
        "messages": [
            {
                "role": "user",
                "content": prompt
            }
        ],
        "temperature": 0.2,
        "max_tokens": max_tokens,

        # ====================================================
        # 关键修改：
        # 关闭 Qwen3 Thinking，避免长文本生成时大量消耗
        # 推理时间，导致 120 秒请求超时。
        # ====================================================
        "enable_thinking": False
    }

    data = json.dumps(
        payload,
        ensure_ascii=False
    ).encode("utf-8")

    last_error = None

    for attempt in range(
        1,
        MAX_RETRIES + 1
    ):

        print(
            f"\n正在调用 SiliconFlow，"
            f"第 {attempt}/{MAX_RETRIES} 次..."
        )

        # ----------------------------------------------------
        # 每一次重试都重新创建 Request
        # ----------------------------------------------------

        request = urllib.request.Request(
            SILICONFLOW_URL,
            data=data,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "Authorization": (
                    f"Bearer {SILICONFLOW_API_KEY}"
                ),
                "User-Agent": (
                    "AI-News-Automation/1.0"
                )
            },
            method="POST"
        )

        try:

            with urllib.request.urlopen(
                request,
                timeout=REQUEST_TIMEOUT
            ) as response:

                response_data = response.read()

            # ------------------------------------------------
            # JSON 解析
            # ------------------------------------------------

            try:

                result = json.loads(
                    response_data.decode("utf-8")
                )

            except json.JSONDecodeError as e:

                raise RuntimeError(
                    f"SiliconFlow 返回数据不是有效 JSON：{e}"
                )

            # ------------------------------------------------
            # 获取模型输出
            # ------------------------------------------------

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

            return content

        # ----------------------------------------------------
        # HTTP 错误
        # ----------------------------------------------------

        except urllib.error.HTTPError as e:

            status = e.code

            error_body = ""

            try:
                error_body = e.read().decode(
                    "utf-8",
                    errors="replace"
                )
            except Exception:
                pass

            error_body = error_body[:1000]

            last_error = RuntimeError(
                f"HTTP {status}"
                + (
                    f"：{error_body}"
                    if error_body
                    else ""
                )
            )

            print(
                f"SiliconFlow HTTP 错误："
                f"{status}"
            )

            if error_body:

                print(
                    f"服务端信息：{error_body}"
                )

            # 401 / 403 等认证错误没必要重复请求
            if not is_retryable_http_status(status):

                raise last_error

        # ----------------------------------------------------
        # 超时
        # ----------------------------------------------------

        except (
            socket.timeout,
            TimeoutError
        ) as e:

            last_error = e

            print(
                f"SiliconFlow 请求超时："
                f"{REQUEST_TIMEOUT} 秒内未完成响应读取"
            )

        # ----------------------------------------------------
        # 网络连接错误
        # ----------------------------------------------------

        except urllib.error.URLError as e:

            last_error = e

            print(
                f"SiliconFlow 网络错误：{e}"
            )

        # ----------------------------------------------------
        # 其他错误
        # ----------------------------------------------------

        except Exception as e:

            last_error = e

            print(
                f"SiliconFlow 调用失败：{e}"
            )

        # ----------------------------------------------------
        # 重试
        # ----------------------------------------------------

        if attempt < MAX_RETRIES:

            print(
                f"{RETRY_WAIT_SECONDS} 秒后自动重试..."
            )

            time.sleep(
                RETRY_WAIT_SECONDS
            )

    raise RuntimeError(
        f"SiliconFlow 连续 "
        f"{MAX_RETRIES} 次调用失败："
        f"{last_error}"
    )


# ============================================================
# 构造新闻上下文
# ============================================================

def build_news_context(
    news_list,
    summary_limit=MAX_SCREENING_SUMMARY_CHARS,
    include_link=False,
    max_total_chars=MAX_SCREENING_CONTEXT_CHARS
):

    lines = []

    current_length = 0

    for index, news in enumerate(
        news_list,
        start=1
    ):

        summary = truncate_text(
            news.get("summary", ""),
            summary_limit
        )

        # ----------------------------------------------------
        # AI 筛选阶段不需要原文链接
        # 因为链接不会影响新闻重要性判断
        # ----------------------------------------------------

        item = (
            f"新闻编号：{index}\n"
            f"来源：{news.get('source', '')}\n"
            f"标题：{news.get('title', '')}\n"
            f"发布时间：{news.get('pub_date', '')}\n"
            f"摘要：{summary}"
        )

        if include_link:

            item += (
                f"\n原文链接："
                f"{news.get('link', '')}"
            )

        # ----------------------------------------------------
        # 控制整个 Prompt 大小
        # ----------------------------------------------------

        if (
            current_length
            + len(item)
            > max_total_chars
        ):

            print(
                f"AI 新闻上下文达到 "
                f"{max_total_chars} 字符限制，"
                f"后续新闻不再发送。"
            )

            break

        lines.append(item)

        current_length += len(item)

    print(
        f"发送给 AI 的新闻上下文长度："
        f"{current_length} 字符"
    )

    return "\n\n--------------------\n\n".join(
        lines
    )


# ============================================================
# AI 新闻筛选
# ============================================================

def ask_ai(news_list):

    # --------------------------------------------------------
    # 筛选阶段：
    # 只发送标题、来源、发布时间、摘要
    # 不发送原文链接
    #
    # 这样可以明显减少 Prompt 大小。
    # --------------------------------------------------------

    news_context = build_news_context(
        news_list,
        summary_limit=MAX_SCREENING_SUMMARY_CHARS,
        include_link=False,
        max_total_chars=MAX_SCREENING_CONTEXT_CHARS
    )

    prompt = f"""
你是一名严格的科技新闻编辑。

下面是今天从国外科技媒体 RSS 抓取到的新闻。

你的任务是：

从中筛选真正值得中国读者关注的「AI 核心新闻」。

【严格筛选标准】

1. AI 必须是新闻核心，而不是顺带提到 AI。
2. 如果删除“AI”这个词，这篇新闻仍然基本成立，则优先判断为非 AI 新闻。
3. 普通网络安全、云计算、芯片、硬件、商业、人事、融资等新闻，
   如果 AI 不是核心内容，必须排除。
4. AI Agent、AI 模型、LLM、生成式 AI、AI 安全、AI 研究等可以保留。
5. 综合新闻、新闻简报、newsletter、roundup 必须排除。
6. 不要为了凑数量而选择新闻。
7. 同一个事件的不同报道，只保留一个。
8. score 小于 7 的不要选择。
9. 最多选择 5 条候选新闻，最终程序会自动选择其中最重要的 1 条。
10. 宁可少选，也不要选择不够重要的新闻。

【非常重要】

你只能根据下面提供的标题和摘要判断。

不能访问互联网。
不能根据自己的知识补充新闻事实。

【输出要求】

只输出 JSON 数组。

不要输出 Markdown。
不要输出 ```json。
不要输出任何解释文字。

格式：

[
  {{
    "index": 1,
    "is_ai": true,
    "is_major": true,
    "duplicate_group": "简短事件名称",
    "score": 9,
    "reason": "为什么值得关注"
  }}
]

如果没有合适新闻：

[]

新闻：

{news_context}
"""

    # --------------------------------------------------------
    # 筛选结果实际上不需要 1800 tokens
    # JSON 很短，降低最大输出可以减少响应压力
    # --------------------------------------------------------

    result = call_ai(
        prompt,
        max_tokens=1200
    )

    result = result.strip()

    # --------------------------------------------------------
    # 清理可能出现的 Markdown
    # --------------------------------------------------------

    result = re.sub(
        r"^```json\s*",
        "",
        result,
        flags=re.IGNORECASE
    )

    result = re.sub(
        r"^```\s*",
        "",
        result
    )

    result = re.sub(
        r"\s*```$",
        "",
        result
    )

    result = result.strip()

    # --------------------------------------------------------
    # 尝试解析 JSON
    # --------------------------------------------------------

    try:

        return json.loads(result)

    except json.JSONDecodeError:

        match = re.search(
            r"\[[\s\S]*\]",
            result
        )

        if match:

            try:

                return json.loads(
                    match.group(0)
                )

            except Exception:
                pass

        print(
            "AI 筛选结果无法解析为 JSON："
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

    roundup_keywords = [
        "the download",
        "newsletter",
        "weekly roundup",
        "daily roundup",
        "roundup:",
        "and more",
        "this week in",
        "today in tech",
        "weekly newsletter",
        "daily newsletter",
    ]

    # --------------------------------------------------------
    # 基础字段检查
    # --------------------------------------------------------

    for item in selected_news:

        try:

            index = int(
                item.get("index", 0)
            )

        except Exception:

            continue

        if (
            index < 1
            or index > len(all_news)
        ):

            print(
                f"过滤：新闻 {index}，"
                f"index 无效"
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
                item.get("score", 0)
            )

        except Exception:

            score = 0

        news = all_news[index - 1]

        title = news["title"].strip()

        title_lower = title.lower()

        # ----------------------------------------------------
        # AI 标记
        # ----------------------------------------------------

        if is_ai is not True:

            print(
                f"过滤：新闻 {index}，"
                f"is_ai={is_ai}"
            )

            continue

        # ----------------------------------------------------
        # 重要性
        # ----------------------------------------------------

        if is_major is not True:

            print(
                f"过滤：新闻 {index}，"
                f"is_major={is_major}"
            )

            continue

        # ----------------------------------------------------
        # 分数
        # ----------------------------------------------------

        if score < 7:

            print(
                f"过滤：新闻 {index}，"
                f"score={score}"
            )

            continue

        # ----------------------------------------------------
        # 综合新闻过滤
        # ----------------------------------------------------

        matched_roundup = False

        for keyword in roundup_keywords:

            if keyword in title_lower:

                print(
                    f"过滤：新闻 {index}，"
                    f"疑似综合型新闻：{title}"
                )

                matched_roundup = True

                break

        if matched_roundup:
            continue

        valid_news.append(item)

    # --------------------------------------------------------
    # 按分数排序
    # --------------------------------------------------------

    valid_news.sort(
        key=lambda x: int(
            x.get("score", 0)
        ),
        reverse=True
    )

    # --------------------------------------------------------
    # 根据 duplicate_group 去重
    # --------------------------------------------------------

    unique_news = []

    duplicate_groups = set()

    for item in valid_news:

        group = str(
            item.get(
                "duplicate_group",
                ""
            )
        ).strip()

        if not group:

            group = (
                f"news-{item['index']}"
            )

        group_key = group.lower()

        if group_key in duplicate_groups:

            print(
                f"过滤：新闻 {item['index']}，"
                f"与其他新闻属于同一事件："
                f"{group}"
            )

            continue

        duplicate_groups.add(
            group_key
        )

        unique_news.append(item)

    # --------------------------------------------------------
    # 最终只保留 1 条最高优先级新闻
    # --------------------------------------------------------

    unique_news = unique_news[:1]

    print(
        f"\n最终保留 "
        f"{len(unique_news)} 条新闻"
    )

    for item in unique_news:

        index = int(
            item["index"]
        )

        news = all_news[index - 1]

        print(
            f"- 新闻 {index} | "
            f"score={item.get('score')} | "
            f"{news['title']}"
        )

    return unique_news


# ============================================================
# AI 提取事实
# ============================================================

def extract_facts(
    selected_news,
    all_news
):

    print(
        "\n========== 开始提取新闻事实 =========="
    )

    news_material = []

    for number, item in enumerate(
        selected_news,
        start=1
    ):

        index = int(
            item["index"]
        )

        news = all_news[index - 1]

        summary = truncate_text(
            news.get("summary", ""),
            MAX_FACT_SUMMARY_CHARS
        )

        news_material.append(
            f"""
新闻编号：{number}

来源：
{news["source"]}

原标题：
{news["title"]}

发布时间：
{news["pub_date"]}

RSS摘要：
{summary}
""".strip()
        )

    context = (
        "\n\n====================\n\n"
        .join(news_material)
    )

    prompt = f"""
你是一名严格的中文科技新闻编辑。

你的任务不是自由创作，而是从下面提供的国外新闻 RSS 信息中，
提取可以安全写进中文公众号文章的事实。

【最高优先级规则】

只能使用下面提供的：

1. 新闻标题
2. RSS摘要
3. 来源
4. 发布时间

绝对不能根据你的知识补充信息。

禁止自行添加：

- 新闻原文中没有出现的人名
- 新闻原文中没有出现的数字
- 新闻原文中没有出现的时间
- 新闻原文中没有出现的公司内部信息
- 新闻原文中没有出现的实验结果
- 新闻原文中没有出现的专家观点
- 新闻原文中没有出现的技术细节
- 新闻原文中没有出现的原因
- 新闻原文中没有出现的后果
- 新闻原文中没有出现的市场影响
- 新闻原文中没有出现的评价
- 新闻原文中没有出现的“业内认为”
- 新闻原文中没有出现的“这意味着”
- 新闻原文中没有出现的未来预测

尤其禁止使用：

“据报道”
“业内认为”
“这意味着”
“值得注意的是”
“被视为”
“标志着”
“重新定义”
“或将”
“有望”
“引发广泛关注”

除非这些内容本身明确存在于 RSS 摘要中。

【重要】

如果 RSS 摘要只有一句话，
就只能基于这一句话写。

不要为了让文章看起来丰富而补充内容。

【输出要求】

只输出 JSON。

不要输出 Markdown。
不要输出 ```json。
不要输出解释。

格式：

{{
  "articles": [
    {{
      "number": 1,
      "title": "准确、简洁的中文标题",
      "facts": [
        "RSS明确提到的事实1。",
        "RSS明确提到的事实2。"
      ]
    }}
  ]
}}

每条新闻：

- title 最多 30 个汉字
- facts 最多 3 条
- 每条 fact 尽量简洁
- 如果 RSS 信息不足，只写 1 条
- 绝对不要为了凑内容增加事实

新闻资料：

{context}
"""

    # --------------------------------------------------------
    # 事实提取只处理 1 条新闻
    # 1200 tokens 已经足够
    # --------------------------------------------------------

    result = call_ai(
        prompt,
        max_tokens=1200
    )

    result = result.strip()

    result = re.sub(
        r"^```json\s*",
        "",
        result,
        flags=re.IGNORECASE
    )

    result = re.sub(
        r"^```\s*",
        "",
        result
    )

    result = re.sub(
        r"\s*```$",
        "",
        result
    )

    result = result.strip()

    try:

        data = json.loads(
            result
        )

    except json.JSONDecodeError:

        match = re.search(
            r"\{[\s\S]*\}",
            result
        )

        if match:

            try:

                data = json.loads(
                    match.group(0)
                )

            except Exception:

                data = {}

        else:

            data = {}

    articles = data.get(
        "articles",
        []
    )

    if not isinstance(
        articles,
        list
    ):

        print(
            "AI 事实提取结果格式异常"
        )

        return []

    print(
        f"\nAI 提取到 "
        f"{len(articles)} 条新闻事实"
    )

    return articles


# ============================================================
# 清理 AI 输出中的链接和 Markdown
# ============================================================

def clean_generated_text(text):

    if not text:
        return ""

    # 删除 Markdown 链接
    text = re.sub(
        r"\[([^\]]+)\]\((https?://[^)]+)\)",
        r"\1",
        text
    )

    # 删除裸 URL
    text = re.sub(
        r"https?://\S+",
        "",
        text
    )

    # 删除来源信息
    text = re.sub(
        r"来源\s*[：:]\s*[^\n]+",
        "",
        text
    )

    # 删除原文信息
    text = re.sub(
        r"原文\s*[：:]\s*[^\n]+",
        "",
        text
    )

    # 压缩多余空行
    text = re.sub(
        r"\n{3,}",
        "\n\n",
        text
    )

    return text.strip()


# ============================================================
# Python 生成公众号文章
# ============================================================

def generate_article(
    selected_news,
    all_news,
    extracted_articles
):

    print(
        "\n========== 开始生成公众号文章 =========="
    )

    if not selected_news:

        return (
            "【今日AI资讯】\n\n"
            f"今天是{get_beijing_date()}，"
            "暂时没有筛选到适合发布的 AI 主题。"
        )

    # --------------------------------------------------------
    # 当前方案：
    # 每天只围绕 1 个最重要的 AI 新闻
    # 写 1 篇完整文章
    # --------------------------------------------------------

    selected = selected_news[0]

    index = int(
        selected["index"]
    )

    news = all_news[index - 1]

    # --------------------------------------------------------
    # 找到对应的事实提取结果
    # --------------------------------------------------------

    article_data = {}

    for item in extracted_articles:

        try:

            number = int(
                item.get(
                    "number",
                    0
                )
            )

        except Exception:

            continue

        if number == 1:

            article_data = item

            break

    facts = article_data.get(
        "facts",
        []
    )

    if not isinstance(
        facts,
        list
    ):

        facts = []

    facts = [
        clean_generated_text(
            str(fact)
        )
        for fact in facts
        if str(fact).strip()
    ]

    facts = [
        fact
        for fact in facts
        if fact
    ]

    facts_text = "\n".join(
        f"- {fact}"
        for fact in facts
    )

    today = get_beijing_date()

    # --------------------------------------------------------
    # 给 AI 的写作资料
    # --------------------------------------------------------

    summary = truncate_text(
        news.get("summary", ""),
        MAX_ARTICLE_SUMMARY_CHARS
    )

    material = f"""
日期：
{today}

来源：
{news["source"]}

原标题：
{news["title"]}

发布时间：
{news["pub_date"]}

RSS摘要：
{summary}

已经确认的事实：
{facts_text if facts_text else "没有额外事实，只能使用原标题和RSS摘要。"}
""".strip()

    prompt = f"""
你是一名中文科技公众号的资深编辑。

今天的文章不是新闻列表，而是只围绕下面这一个 AI 新闻主题，
写成一篇完整、自然、适合微信公众号阅读的原创中文文章。

【唯一新闻主题】

{material}

==================================================
【最重要的事实边界】
==================================================

你只能使用上面提供的新闻标题、RSS摘要和“已经确认的事实”。

绝对不能：

- 使用你自己的知识补充新闻细节
- 编造人名、数字、日期、公司内部信息
- 编造实验结果、benchmark、论文内容
- 编造专家观点、业内观点
- 编造新闻原文没有出现的技术细节
- 编造新闻原文没有出现的后果或市场影响
- 把自己的推测写成事实
- 虚构新闻背景

如果资料中没有某个信息，就不要写具体细节。

可以做“编辑层面的分析”，但必须明确这是分析或思考，
不能把分析写成新闻事实。

例如：

“如果从更大的 AI 发展趋势来看，这件事值得关注的地方在于……”

这种表达可以使用。

但不能写：

“这意味着 AI 已经能够……”

除非资料明确支持。

==================================================
【文章目标】
==================================================

不要写成：

- 新闻1
- 新闻2
- 新闻3
- 事实1
- 事实2
- 事实3

必须写成“一篇完整的公众号文章”。

建议文章结构：

1. 一个有吸引力的标题

2. 开头导语
   用 2～4 段把读者带入这个事件。
   第一段尽量有冲击力，但不能夸张到超出事实。

3. 发生了什么？
   用 2～4 段讲清楚这条新闻本身。
   这里必须严格依据资料。

4. 为什么这件事值得关注？
   结合已经确认的事实进行解释。
   可以加入合理分析，但必须明确是分析，不要伪装成事实。

5. 这背后反映了什么？
   从 AI 技术发展、AI Agent、模型能力、AI 安全、
   AI 应用等角度选择与这条新闻真正相关的方向进行分析。
   不相关的方向不要硬凑。

6. 对普通开发者/AI 从业者有什么启发？
   只有在确实适合的情况下写。
   不要为了凑字数强行联系开发者。

7. 写在最后
   用 1～3 段自然收束全文。

==================================================
【写作风格】
==================================================

参考优秀中文技术公众号的阅读体验：

- 口语化，但不要低幼
- 有观点，但不要哗众取宠
- 有技术信息，但解释要让普通技术读者看得懂
- 段落不要太长
- 小标题清晰
- 可以使用加粗标记突出关键概念
- 有自然的转折和过渡
- 不要每一段都用“首先、其次、最后”
- 不要出现明显的 AI 套话
- 不要写“本文将……”
- 不要写“让我们拭目以待”
- 不要写“值得我们深思”
- 不要写“在当今这个快速发展的时代”
- 不要写“这标志着……”
  除非资料明确支持这种判断

文章目标长度：

约 1500～2200 个中文字符。

如果资料不足以支持这么长，
宁可短一些，也不能编造事实。

==================================================
【输出格式】
==================================================

只输出文章正文。

第一行是文章标题。

然后直接开始正文。

不要输出：

- Markdown代码块
- JSON
- “来源”
- “原文链接”
- 新闻编号
- 写作说明
- 事实列表

来源和原文链接由程序自动添加。

现在开始写。
"""

    # --------------------------------------------------------
    # 文章目标 1500～2200 字
    # 2800 tokens 已经给出足够空间
    # 同时减少模型无意义的超长生成
    # --------------------------------------------------------

    result = call_ai(
        prompt,
        max_tokens=2800
    )

    result = result.strip()

    # --------------------------------------------------------
    # 清理可能出现的 Markdown 代码块
    # --------------------------------------------------------

    result = re.sub(
        r"^```(?:markdown|text)?\s*",
        "",
        result,
        flags=re.IGNORECASE
    )

    result = re.sub(
        r"\s*```$",
        "",
        result
    )

    result = result.strip()

    # --------------------------------------------------------
    # 清理 AI 自己可能生成的来源/链接
    # --------------------------------------------------------

    result = clean_generated_text(
        result
    )

    if not result:

        result = news["title"]

    # --------------------------------------------------------
    # Python 自动追加来源和原文链接
    #
    # 防止 AI 修改、遗漏或编造链接
    # --------------------------------------------------------

    article = (
        f"{result}\n\n"
        f"---\n\n"
        f"**来源：** {news['source']}\n\n"
        f"**原文：** {news['link']}"
    )

    return article.strip()


# ============================================================
# 主程序
# ============================================================

def main():

    print(
        "\n========================================"
    )

    print(
        "\n        AI 新闻自动化系统启动"
    )

    print(
        "\n========================================"
    )

    # --------------------------------------------------------
    # 第一步：抓取 RSS
    # --------------------------------------------------------

    all_news = []

    for source_name, rss_url in RSS_SOURCES.items():

        news_list = fetch_rss(
            source_name,
            rss_url
        )

        all_news.extend(
            news_list
        )

    print(
        f"\n========== RSS 总新闻数："
        f"{len(all_news)} =========="
    )

    if not all_news:

        print(
            "\n没有抓取到任何新闻，程序结束。"
        )

        return

    # --------------------------------------------------------
    # 第二步：AI 筛选
    # --------------------------------------------------------

    selected_news = ask_ai(
        all_news
    )

    print(
        "\n========== AI 原始筛选结果 =========="
    )

    print(
        json.dumps(
            selected_news,
            ensure_ascii=False,
            indent=2
        )
    )

    # --------------------------------------------------------
    # 第三步：程序二次过滤
    # --------------------------------------------------------

    selected_news = filter_selected_news(
        selected_news,
        all_news
    )

    # --------------------------------------------------------
    # 没有新闻
    # --------------------------------------------------------

    if not selected_news:

        print(
            "\n今天没有筛选到符合要求的 AI 新闻。"
        )

        print(
            "\n========================================"
        )

        print(
            "\nAI 新闻自动化流程执行完成"
        )

        print(
            "\n========================================"
        )

        return

    # --------------------------------------------------------
    # 第四步：AI 提取事实
    # --------------------------------------------------------

    extracted_articles = extract_facts(
        selected_news,
        all_news
    )

    print(
        "\n========== AI 事实提取结果 =========="
    )

    print(
        json.dumps(
            extracted_articles,
            ensure_ascii=False,
            indent=2
        )
    )

    # --------------------------------------------------------
    # 第五步：AI 生成完整公众号文章
    # --------------------------------------------------------

    article = generate_article(
        selected_news,
        all_news,
        extracted_articles
    )

    print(
        "\n========== AI 公众号文章 ==========\n"
    )

    print(article)

    print(
        "\n========================================"
    )

    print(
        "\nAI 新闻自动化流程执行完成"
    )

    print(
        "\n========================================"
    )


# ============================================================
# 程序入口
# ============================================================

if __name__ == "__main__":
    main()
