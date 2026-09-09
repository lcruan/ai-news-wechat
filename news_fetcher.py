import os
import re
import json
import time
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
        with urllib.request.urlopen(request, timeout=60) as response:
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
        entries = root.findall(".//{http://www.w3.org/2005/Atom}entry")

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
                title = clean_text(title_node.text or "")

            if summary_node is not None:
                summary = clean_text(summary_node.text or "")

            if not summary and content_node is not None:
                summary = clean_text(content_node.text or "")

            if published_node is not None:
                pub_date = clean_text(published_node.text or "")
            elif updated_node is not None:
                pub_date = clean_text(updated_node.text or "")

            link_nodes = entry.findall(
                "{http://www.w3.org/2005/Atom}link"
            )

            for link_node in link_nodes:
                href = link_node.attrib.get("href", "")

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

    print(f"抓取到 {len(news_list)} 条新闻")

    return news_list


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
        "max_tokens": max_tokens
    }

    data = json.dumps(payload).encode("utf-8")

    request = urllib.request.Request(
        SILICONFLOW_URL,
        data=data,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {SILICONFLOW_API_KEY}"
        },
        method="POST"
    )

    last_error = None

    for attempt in range(1, MAX_RETRIES + 1):

        print(
            f"\n正在调用 SiliconFlow，第 {attempt}/{MAX_RETRIES} 次..."
        )

        try:

            with urllib.request.urlopen(
                request,
                timeout=REQUEST_TIMEOUT
            ) as response:

                response_data = response.read()

            result = json.loads(response_data.decode("utf-8"))

            content = (
                result
                .get("choices", [{}])[0]
                .get("message", {})
                .get("content", "")
            )

            if not content:
                raise RuntimeError("SiliconFlow 返回内容为空")

            print("SiliconFlow 调用成功")

            return content

        except Exception as e:

            last_error = e

            print(f"SiliconFlow 调用失败：{e}")

            if attempt < MAX_RETRIES:
                print(
                    f"{RETRY_WAIT_SECONDS} 秒后自动重试..."
                )
                time.sleep(RETRY_WAIT_SECONDS)

    raise RuntimeError(
        f"SiliconFlow 连续 {MAX_RETRIES} 次调用失败：{last_error}"
    )


# ============================================================
# 构造新闻上下文
# ============================================================

def build_news_context(news_list):

    lines = []

    for index, news in enumerate(news_list, start=1):

        lines.append(
            f"""
新闻编号：{index}
来源：{news["source"]}
标题：{news["title"]}
发布时间：{news["pub_date"]}
摘要：{news["summary"]}
原文链接：{news["link"]}
""".strip()
        )

    return "\n\n--------------------\n\n".join(lines)


# ============================================================
# AI 新闻筛选
# ============================================================

def ask_ai(news_list):

    news_context = build_news_context(news_list)

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
9. 最多选择 5 条。
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

    result = call_ai(prompt, max_tokens=1800)

    # --------------------------------------------------------
    # 清理可能出现的 Markdown
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # 尝试提取 JSON
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
                return json.loads(match.group(0))
            except Exception:
                pass

        print("AI 筛选结果无法解析为 JSON：")
        print(result)

        return []


# ============================================================
# 程序二次过滤
# ============================================================

def filter_selected_news(selected_news, all_news):

    print("\n========== 程序二次过滤 ==========")

    valid_news = []

    # --------------------------------------------------------
    # 综合型新闻关键词
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

    # --------------------------------------------------------
    # 基础字段检查
    # --------------------------------------------------------

    for item in selected_news:

        try:
            index = int(item.get("index", 0))
        except Exception:
            continue

        if index < 1 or index > len(all_news):

            print(
                f"过滤：新闻 {index}，index 无效"
            )

            continue

        is_ai = item.get("is_ai", False)
        is_major = item.get("is_major", False)

        try:
            score = int(item.get("score", 0))
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
                f"过滤：新闻 {index}，is_ai={is_ai}"
            )

            continue

        # ----------------------------------------------------
        # 重要性
        # ----------------------------------------------------

        if is_major is not True:

            print(
                f"过滤：新闻 {index}，is_major={is_major}"
            )

            continue

        # ----------------------------------------------------
        # 分数
        # ----------------------------------------------------

        if score < 7:

            print(
                f"过滤：新闻 {index}，score={score}"
            )

            continue

        # ----------------------------------------------------
        # 综合新闻过滤
        # ----------------------------------------------------

        matched_roundup = False

        for keyword in roundup_keywords:

            if keyword in title_lower:

                print(
                    f"过滤：新闻 {index}，疑似综合型新闻：{title}"
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
        key=lambda x: int(x.get("score", 0)),
        reverse=True
    )

    # --------------------------------------------------------
    # 根据 duplicate_group 去重
    # --------------------------------------------------------

    unique_news = []

    duplicate_groups = set()

    for item in valid_news:

        group = str(
            item.get("duplicate_group", "")
        ).strip()

        if not group:

            group = f"news-{item['index']}"

        group_key = group.lower()

        if group_key in duplicate_groups:

            print(
                f"过滤：新闻 {item['index']}，"
                f"与其他新闻属于同一事件：{group}"
            )

            continue

        duplicate_groups.add(group_key)

        unique_news.append(item)

    # --------------------------------------------------------
    # 最多 5 条
    # --------------------------------------------------------

    unique_news = unique_news[:5]

    print(
        f"\n最终保留 {len(unique_news)} 条新闻"
    )

    for item in unique_news:

        index = int(item["index"])

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

def extract_facts(selected_news, all_news):

    print(
        "\n========== 开始提取新闻事实 =========="
    )

    news_material = []

    for number, item in enumerate(
        selected_news,
        start=1
    ):

        index = int(item["index"])

        news = all_news[index - 1]

        news_material.append(
            f"""
新闻编号：{number}

来源：{news["source"]}

原标题：
{news["title"]}

发布时间：
{news["pub_date"]}

RSS摘要：
{news["summary"]}
""".strip()
        )

    context = "\n\n====================\n\n".join(
        news_material
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

    result = call_ai(
        prompt,
        max_tokens=2200
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

        data = json.loads(result)

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

    articles = data.get("articles", [])

    if not isinstance(articles, list):

        print(
            "AI 事实提取结果格式异常"
        )

        return []

    print(
        f"\nAI 提取到 {len(articles)} 条新闻事实"
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

    text = re.sub(
        r"原文\s*[：:]\s*[^\n]+",
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
# Python 生成公众号文章
# ============================================================

def generate_article(selected_news, all_news, extracted_articles):

    print(
        "\n========== 开始生成公众号文章 =========="
    )

    article_map = {}

    for item in extracted_articles:

        try:
            number = int(item.get("number", 0))
        except Exception:
            continue

        article_map[number] = item

    today = get_beijing_date()

    lines = []

    lines.append("【今日AI资讯】")
    lines.append("")
    lines.append(
        f"今天是{today}，整理几条值得关注的 AI 资讯。"
    )
    lines.append("")

    article_number = 0

    for number, selected in enumerate(
        selected_news,
        start=1
    ):

        if number not in article_map:
            continue

        article_data = article_map[number]

        title = clean_generated_text(
            str(
                article_data.get(
                    "title",
                    ""
                )
            )
        )

        facts = article_data.get(
            "facts",
            []
        )

        if not title:
            continue

        if not isinstance(facts, list):
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

        if not facts:
            continue

        index = int(selected["index"])

        news = all_news[index - 1]

        article_number += 1

        lines.append(
            f"【新闻{article_number}】"
        )
        lines.append("")

        lines.append(title)
        lines.append("")

        for fact in facts:

            lines.append(fact)
            lines.append("")

        lines.append(
            f"来源：{news['source']}"
        )

        lines.append(
            f"原文：{news['link']}"
        )

        lines.append("")

    if article_number == 0:

        return (
            "【今日AI资讯】\n\n"
            f"今天是{today}，"
            "暂时没有筛选到适合发布的 AI 资讯。"
        )

    article = "\n".join(lines)

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

        all_news.extend(news_list)

    print(
        f"\n========== RSS 总新闻数：{len(all_news)} =========="
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
    # 第五步：Python 组装公众号文章
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
