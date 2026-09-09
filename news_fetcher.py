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

RSS_SOURCES = {
    "Ars Technica": "https://feeds.arstechnica.com/arstechnica/technology-lab",
    "MIT Technology Review": "https://www.technologyreview.com/feed/",
}

SILICONFLOW_API_URL = "https://api.siliconflow.cn/v1/chat/completions"
SILICONFLOW_MODEL = "Qwen/Qwen3-8B"

# 请求超时时间：120 秒
REQUEST_TIMEOUT = 120

# 最多重试 3 次
MAX_RETRIES = 3

# 每次失败后等待 5 秒
RETRY_WAIT_SECONDS = 5

# 最多保留 5 条新闻
MAX_NEWS = 5


# ============================================================
# 文本清洗
# ============================================================

def clean_text(text):
    if not text:
        return ""

    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    text = text.replace("&nbsp;", " ")
    text = text.replace("&amp;", "&")
    text = text.replace("&quot;", '"')
    text = text.replace("&#39;", "'")
    text = text.strip()

    return text


# ============================================================
# 获取北京时间
# ============================================================

def get_beijing_date():
    beijing_timezone = timezone(timedelta(hours=8))
    now = datetime.now(beijing_timezone)
    return now.strftime("%Y年%m月%d日")


# ============================================================
# RSS 抓取
# ============================================================

def fetch_rss(source_name, rss_url):
    print(f"\n========== 开始抓取：{source_name} ==========")
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
            timeout=REQUEST_TIMEOUT
        ) as response:
            data = response.read()

        root = ET.fromstring(data)

        news_list = []

        # --------------------------------------------------------
        # RSS 格式
        # --------------------------------------------------------

        items = root.findall(".//item")

        for item in items:
            title_element = item.find("title")
            description_element = item.find("description")
            link_element = item.find("link")
            pub_date_element = item.find("pubDate")

            title = clean_text(
                title_element.text if title_element is not None else ""
            )

            summary = clean_text(
                description_element.text
                if description_element is not None
                else ""
            )

            link = (
                link_element.text.strip()
                if link_element is not None and link_element.text
                else ""
            )

            pub_date = (
                pub_date_element.text.strip()
                if pub_date_element is not None and pub_date_element.text
                else ""
            )

            if title:
                news_list.append({
                    "source": source_name,
                    "title": title,
                    "summary": summary,
                    "link": link,
                    "pub_date": pub_date,
                })

        # --------------------------------------------------------
        # Atom 格式
        # --------------------------------------------------------

        if not news_list:
            namespaces = {
                "atom": "http://www.w3.org/2005/Atom"
            }

            entries = root.findall(".//atom:entry", namespaces)

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

                title = clean_text(
                    title_element.text
                    if title_element is not None
                    else ""
                )

                summary = ""

                if summary_element is not None:
                    summary = clean_text(
                        summary_element.text or ""
                    )

                if not summary and content_element is not None:
                    summary = clean_text(
                        content_element.text or ""
                    )

                link = ""

                link_elements = entry.findall(
                    "atom:link",
                    namespaces
                )

                for link_element in link_elements:
                    href = link_element.attrib.get("href", "")

                    if href:
                        link = href
                        break

                pub_date = ""

                if published_element is not None:
                    pub_date = (
                        published_element.text or ""
                    ).strip()

                if not pub_date and updated_element is not None:
                    pub_date = (
                        updated_element.text or ""
                    ).strip()

                if title:
                    news_list.append({
                        "source": source_name,
                        "title": title,
                        "summary": summary,
                        "link": link,
                        "pub_date": pub_date,
                    })

        print(f"抓取到 {len(news_list)} 条新闻")

        return news_list

    except Exception as e:
        print(f"RSS 抓取失败：{e}")
        return []


# ============================================================
# SiliconFlow AI 请求
# ============================================================

def call_ai(prompt):
    api_key = os.environ.get("SILICONFLOW_API_KEY")

    if not api_key:
        raise RuntimeError(
            "没有找到 SILICONFLOW_API_KEY，请检查 GitHub Secrets。"
        )

    payload = {
        "model": SILICONFLOW_MODEL,
        "messages": [
            {
                "role": "user",
                "content": prompt
            }
        ],
        "temperature": 0.2,
        "max_tokens": 1800
    }

    request_data = json.dumps(
        payload,
        ensure_ascii=False
    ).encode("utf-8")

    request = urllib.request.Request(
        SILICONFLOW_API_URL,
        data=request_data,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
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
                timeout=REQUEST_TIMEOUT
            ) as response:

                response_data = response.read()

            result = json.loads(
                response_data.decode("utf-8")
            )

            choices = result.get("choices", [])

            if not choices:
                raise RuntimeError(
                    f"AI 返回结果异常：{result}"
                )

            message = choices[0].get("message", {})

            content = message.get("content", "")

            if not content:
                raise RuntimeError(
                    "AI 返回内容为空。"
                )

            print("SiliconFlow 调用成功")

            return content.strip()

        except Exception as e:
            last_error = e

            print(
                f"SiliconFlow 调用失败：{e}"
            )

            if attempt < MAX_RETRIES:
                print(
                    f"{RETRY_WAIT_SECONDS} 秒后自动重试..."
                )
                time.sleep(RETRY_WAIT_SECONDS)

    raise RuntimeError(
        f"SiliconFlow 连续 {MAX_RETRIES} 次调用失败："
        f"{last_error}"
    )


# ============================================================
# 构造新闻上下文
# ============================================================

def build_news_context(news_list):
    context_parts = []

    for index, news in enumerate(
        news_list,
        start=1
    ):
        context_parts.append(
            f"""
新闻 {index}

来源：
{news["source"]}

标题：
{news["title"]}

摘要：
{news["summary"]}

发布时间：
{news["pub_date"]}

原文链接：
{news["link"]}
""".strip()
        )

    return "\n\n==============================\n\n".join(
        context_parts
    )


# ============================================================
# AI 筛选新闻
# ============================================================

def ask_ai(news_list):
    print(
        "\n========== 开始 AI 新闻筛选 =========="
    )

    if not news_list:
        return []

    news_context = build_news_context(
        news_list
    )

    prompt = f"""
你是一名严格的 AI 科技新闻编辑。

请从下面的新闻中筛选真正值得发布到“AI科技资讯”公众号的新闻。

==============================
筛选原则
==============================

1. AI 必须是新闻的核心主题。

2. 如果把“AI”两个字从新闻中删除，
   这篇新闻仍然完全成立，
   那么通常应该判定为非 AI 新闻。

3. 严格排除：
   - 普通网络安全新闻
   - 普通软件更新
   - 普通云计算新闻
   - 普通硬件新闻
   - 普通机器人新闻
   - 普通商业新闻
   - 普通公司新闻
   - 普通科技新闻
   - AI 只是顺带被提到的新闻
   - 综合新闻
   - 新闻简报
   - Newsletter
   - Weekly roundup
   - The Download
   - “and more” 类型文章

4. AI Agent、生成式 AI、大模型、AI 安全、
   AI 科研、AI 产品、AI 公司重大动态等，
   可以作为 AI 新闻。

5. 新闻必须具有一定行业价值或关注价值。

6. score 必须达到 7 分或以上。

7. 不要为了凑够 5 条而选择质量一般的新闻。

8. 如果只有 2 条符合要求，就只返回 2 条。

9. 如果只有 1 条符合要求，就只返回 1 条。

10. 如果没有符合要求的新闻，返回空数组 []。

11. 如果多个新闻明显属于同一个事件，
    duplicate_group 使用相同的名称。

12. 不要根据你的知识补充新闻事实。
    只能根据我提供的标题、摘要和来源进行判断。

==============================
特别注意
==============================

例如：

“OpenAI 发布新的 AI Agent”
属于 AI 核心新闻。

“微软修复大量安全漏洞，其中一个漏洞涉及 AI”
通常不属于 AI 核心新闻。

“某机器人公司使用 AI”
如果新闻核心是机器人产品，
而不是 AI 技术本身，
通常也不要选择。

“The Download: xxx and more”
属于综合新闻，不要选择。

==============================
输出格式
==============================

只输出 JSON 数组。

格式必须严格类似：

[
  {{
    "index": 1,
    "is_ai": true,
    "is_major": true,
    "duplicate_group": "xxx",
    "score": 9,
    "reason": "AI是新闻核心，具有较高行业关注价值"
  }}
]

不要输出 Markdown。
不要输出 ```json。
不要输出任何解释。

==============================
新闻列表
==============================

{news_context}
"""

    result = call_ai(prompt)

    print(
        "\n========== AI 原始筛选结果 ==========\n"
    )

    print(result)

    try:
        result = result.strip()

        # 防止模型偶尔返回 ```json
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

        selected_news = json.loads(
            result
        )

        if not isinstance(
            selected_news,
            list
        ):
            print("AI 返回结果不是数组")
            return []

        return selected_news

    except Exception as e:
        print(
            f"AI 筛选结果 JSON 解析失败：{e}"
        )

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
    # 综合型文章关键词
    # --------------------------------------------------------

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

    for item in selected_news:

        try:
            index = int(
                item.get("index", 0)
            )
        except Exception:
            continue

        if index < 1 or index > len(all_news):
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
                item.get("score", 0)
            )
        except Exception:
            score = 0

        title = all_news[
            index - 1
        ]["title"]

        title_lower = title.lower()

        # ----------------------------------------------------
        # AI 标记过滤
        # ----------------------------------------------------

        if is_ai is not True:
            print(
                f"过滤：新闻 {index}，"
                f"is_ai={is_ai}"
            )
            continue

        # ----------------------------------------------------
        # 重大程度过滤
        # ----------------------------------------------------

        if is_major is not True:
            print(
                f"过滤：新闻 {index}，"
                f"is_major={is_major}"
            )
            continue

        # ----------------------------------------------------
        # 分数过滤
        # ----------------------------------------------------

        if score < 7:
            print(
                f"过滤：新闻 {index}，"
                f"score={score}"
            )
            continue

        # ----------------------------------------------------
        # 综合文章过滤
        # ----------------------------------------------------

        is_roundup = False

        for keyword in roundup_keywords:
            if keyword in title_lower:
                is_roundup = True
                break

        if is_roundup:
            print(
                f"过滤：新闻 {index}，"
                f"疑似综合型文章：{title}"
            )
            continue

        valid_news.append(item)

    # --------------------------------------------------------
    # duplicate_group 去重
    # --------------------------------------------------------

    valid_news.sort(
        key=lambda x: int(
            x.get("score", 0)
        ),
        reverse=True
    )

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

        if group in duplicate_groups:
            print(
                f"过滤：新闻 {item['index']}，"
                f"与其他新闻属于同一事件："
                f"{group}"
            )
            continue

        duplicate_groups.add(group)

        unique_news.append(item)

    unique_news = unique_news[
        :MAX_NEWS
    ]

    print(
        f"\n最终保留 "
        f"{len(unique_news)} 条新闻"
    )

    for item in unique_news:

        index = int(
            item["index"]
        )

        print(
            f"- 新闻 {index} | "
            f"score={item.get('score')} | "
            f"{all_news[index - 1]['title']}"
        )

    return unique_news


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

    if not selected_news:
        return (
            "今天暂未筛选到符合要求的 AI 新闻。"
        )

    news_data = []

    for number, item in enumerate(
        selected_news,
        start=1
    ):
        index = int(
            item["index"]
        )

        news = all_news[
            index - 1
        ]

        news_data.append({
            "number": number,
            "source": news["source"],
            "title": news["title"],
            "summary": news["summary"],
            "pub_date": news["pub_date"],
        })

    news_context = build_news_context(
        [
            {
                "source": item["source"],
                "title": item["title"],
                "summary": item["summary"],
                "link": "",
                "pub_date": item["pub_date"],
            }
            for item in news_data
        ]
    )

    today = get_beijing_date()

    prompt = f"""
你是一名中文科技公众号编辑。

请根据我提供的新闻标题、新闻摘要、来源和发布时间，
整理成一篇简洁、自然、适合微信公众号阅读的 AI 新闻资讯文章。

今天日期：
{today}

==============================
最重要的要求：禁止编造事实
==============================

你只能使用我提供的：

- 新闻标题
- 新闻摘要
- 新闻来源
- 发布时间

作为事实依据。

摘要里没有的信息，一律不要写。

绝对禁止自行补充：

- 数字
- 数据
- 专家观点
- 专家姓名
- 公司内部信息
- 内部人士
- 采访内容
- 技术细节
- 产品参数
- 事件原因
- 事件后果
- 市场影响
- 用户数量
- 融资金额
- 时间线
- 公司声明
- “业内认为”
- “业内人士表示”
- “这意味着”
- “这标志着”
- 任何你自己推测出来的内容

如果摘要为空，
只能根据标题非常保守地介绍，
不要扩展事实。

==============================
写作风格
==============================

1. 中文自然。

2. 像人工编辑写的科技资讯，
   不要有明显 AI 腔。

3. 简洁，不要啰嗦。

4. 不要大量使用：
   “值得注意的是”
   “这意味着”
   “重新定义”
   “引发广泛关注”
   “业内人士认为”
   等模板化表达。

5. 不要为了显得专业而增加不存在的信息。

6. 每条新闻控制在 1～2 个自然段。

7. 新闻标题可以在不改变事实的情况下，
   做轻微中文化改写。

8. 不要虚构新闻标题没有表达的具体结论。

9. 开头只需要简单介绍今天整理了几条 AI 新闻，
   不要提前总结具体事件。

10. 文章不要写结束语。

==============================
文章格式
==============================

开头：

【今日AI资讯】

今天是{today}，整理几条值得关注的 AI 资讯。

然后按照：

【新闻1】
标题

正文

【新闻2】
标题

正文

依次输出。

不要输出来源。
不要输出原文链接。

来源和原文链接由 Python 程序自动添加。

==============================
输出要求
==============================

直接输出正文。

不要输出：

```markdown
不要输出 ```json
不要输出任何解释。
不要输出“以下是文章”。
不要输出“好的”。
不要输出文章之外的内容。

==============================
新闻资料
==============================

{news_context}
"""

    article = call_ai(prompt)

    # --------------------------------------------------------
    # 清理模型可能输出的 Markdown 代码围栏
    # --------------------------------------------------------

    article = article.strip()

    article = re.sub(
        r"^```markdown\s*",
        "",
        article,
        flags=re.IGNORECASE
    )

    article = re.sub(
        r"^```\s*",
        "",
        article
    )

    article = re.sub(
        r"\s*```$",
        "",
        article
    )

    # --------------------------------------------------------
    # Python 自动添加来源和 URL
    # --------------------------------------------------------

    source_parts = []

    for number, item in enumerate(
        selected_news,
        start=1
    ):
        index = int(
            item["index"]
        )

        news = all_news[
            index - 1
        ]

        source_parts.append(
            f"""
【新闻{number}来源】

来源：{news["source"]}

原文：{news["link"]}
""".strip()
        )

    if source_parts:
        article += (
            "\n\n\n"
            + "\n\n".join(
                source_parts
            )
        )

    return article


# ============================================================
# 主程序
# ============================================================

def main():

    print(
        "========================================"
    )

    print(
        "        AI News Daily"
    )

    print(
        "========================================"
    )

    # --------------------------------------------------------
    # 第一步：抓取 RSS
    # --------------------------------------------------------

    all_news = []

    for source_name, rss_url in RSS_SOURCES.items():

        news = fetch_rss(
            source_name,
            rss_url
        )

        all_news.extend(news)

    print(
        f"\n========== RSS 抓取完成 =========="
    )

    print(
        f"总共抓取：{len(all_news)} 条新闻"
    )

    if not all_news:
        print(
            "没有抓取到任何新闻，任务结束。"
        )
        return

    # --------------------------------------------------------
    # 第二步：AI 筛选
    # --------------------------------------------------------

    selected_news = ask_ai(
        all_news
    )

    if not selected_news:
        print(
            "\n没有通过 AI 筛选的新闻。"
        )
        return

    # --------------------------------------------------------
    # 第三步：程序二次过滤
    # --------------------------------------------------------

    selected_news = filter_selected_news(
        selected_news,
        all_news
    )

    if not selected_news:
        print(
            "\n程序二次过滤后没有符合要求的新闻。"
        )
        return

    # --------------------------------------------------------
    # 第四步：生成公众号文章
    # --------------------------------------------------------

    article = generate_article(
        selected_news,
        all_news
    )

    print(
        "\n========== AI 公众号文章 ==========\n"
    )

    print(article)

    print(
        "\n========== 任务完成 =========="
    )


# ============================================================
# 程序入口
# ============================================================

if __name__ == "__main__":
    main()
