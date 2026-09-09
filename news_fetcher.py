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

SILICONFLOW_API_KEY = os.getenv("SILICONFLOW_API_KEY")

SILICONFLOW_URL = "https://api.siliconflow.cn/v1/chat/completions"

MODEL = "Qwen/Qwen3-8B"

# 保留之前确定的设置：
# 超时 120 秒
# 最多重试 3 次
# 每次失败等待 5 秒
REQUEST_TIMEOUT = 120
MAX_RETRIES = 3
RETRY_WAIT = 5

RSS_SOURCES = {
    "Ars Technica": "https://feeds.arstechnica.com/arstechnica/technology-lab",
    "MIT Technology Review": "https://www.technologyreview.com/feed/",
}


# ============================================================
# 文本清理
# ============================================================

def clean_text(text):
    if not text:
        return ""

    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)

    return text.strip()


# ============================================================
# 北京时间
# ============================================================

def get_beijing_date():
    beijing_tz = timezone(timedelta(hours=8))
    return datetime.now(beijing_tz).strftime("%Y年%m月%d日")


# ============================================================
# RSS 抓取
# ============================================================

def fetch_rss(source_name, url):
    print(f"\n========== 抓取 {source_name} ==========")
    print(url)

    try:
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 AI-News-Bot"
            }
        )

        with urllib.request.urlopen(
            request,
            timeout=REQUEST_TIMEOUT
        ) as response:

            xml_data = response.read()

        root = ET.fromstring(xml_data)

        news_list = []

        # ----------------------------------------------------
        # RSS <item>
        # ----------------------------------------------------

        items = root.findall(".//item")

        # ----------------------------------------------------
        # Atom <entry>
        # ----------------------------------------------------

        if not items:
            items = root.findall(".//{http://www.w3.org/2005/Atom}entry")

        for item in items:

            title = ""
            summary = ""
            link = ""
            pub_date = ""

            # ----------------------------
            # RSS
            # ----------------------------

            title_node = item.find("title")
            if title_node is not None:
                title = title_node.text or ""

            description_node = item.find("description")
            if description_node is not None:
                summary = description_node.text or ""

            link_node = item.find("link")
            if link_node is not None:
                link = link_node.text or ""

            pub_node = item.find("pubDate")
            if pub_node is not None:
                pub_date = pub_node.text or ""

            # ----------------------------
            # Atom
            # ----------------------------

            if not title:
                title_node = item.find(
                    "{http://www.w3.org/2005/Atom}title"
                )
                if title_node is not None:
                    title = title_node.text or ""

            if not summary:
                summary_node = item.find(
                    "{http://www.w3.org/2005/Atom}summary"
                )

                if summary_node is None:
                    summary_node = item.find(
                        "{http://www.w3.org/2005/Atom}content"
                    )

                if summary_node is not None:
                    summary = summary_node.text or ""

            if not link:
                link_node = item.find(
                    "{http://www.w3.org/2005/Atom}link"
                )

                if link_node is not None:
                    link = link_node.attrib.get("href", "")

            if not pub_date:
                pub_node = item.find(
                    "{http://www.w3.org/2005/Atom}published"
                )

                if pub_node is None:
                    pub_node = item.find(
                        "{http://www.w3.org/2005/Atom}updated"
                    )

                if pub_node is not None:
                    pub_date = pub_node.text or ""

            title = clean_text(title)
            summary = clean_text(summary)
            link = link.strip()
            pub_date = clean_text(pub_date)

            if not title:
                continue

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
# SiliconFlow AI 调用
# ============================================================

def call_ai(prompt, max_tokens=1800):

    if not SILICONFLOW_API_KEY:
        raise RuntimeError(
            "没有找到 SILICONFLOW_API_KEY，请检查 GitHub Secrets"
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

        try:

            print(
                f"\n正在调用 SiliconFlow，第 {attempt}/{MAX_RETRIES} 次..."
            )

            with urllib.request.urlopen(
                request,
                timeout=REQUEST_TIMEOUT
            ) as response:

                response_data = response.read()

            result = json.loads(
                response_data.decode("utf-8")
            )

            content = result["choices"][0]["message"]["content"]

            print("SiliconFlow 调用成功")

            return content.strip()

        except Exception as e:

            last_error = e

            print(f"SiliconFlow 调用失败：{e}")

            if attempt < MAX_RETRIES:
                print(
                    f"{RETRY_WAIT} 秒后自动重试..."
                )
                time.sleep(RETRY_WAIT)

    raise RuntimeError(
        f"SiliconFlow 连续 {MAX_RETRIES} 次调用失败：{last_error}"
    )


# ============================================================
# 构建新闻上下文
# ============================================================

def build_news_context(news_list):

    context = []

    for i, item in enumerate(news_list, start=1):

        context.append(
            f"""
新闻编号：{i}
来源：{item["source"]}
标题：{item["title"]}
发布时间：{item["pub_date"]}
摘要：{item["summary"]}
原文链接：{item["link"]}
""".strip()
        )

    return "\n\n-------------------------\n\n".join(context)


# ============================================================
# AI 新闻筛选
# ============================================================

def ask_ai(news_list):

    news_context = build_news_context(news_list)

    prompt = f"""
你是一名非常严格的国际 AI 科技新闻编辑。

下面是今天抓取到的国外科技媒体 RSS 新闻。

你的任务不是为了凑数量，而是从中挑选真正值得发布的 AI 新闻。

【最重要的判断标准】

一、AI 必须是新闻核心。

判断方法：

“如果把 AI、人工智能、AI Agent、AI 模型等相关内容删除，
这篇新闻是否仍然成立？”

如果删除 AI 后，这篇新闻依然主要是一篇普通的：
- 网络安全新闻
- 企业新闻
- 云计算新闻
- 芯片新闻
- 硬件新闻
- 机器人新闻
- 商业新闻
- 产品新闻

则必须：
is_ai = false

二、只选择具有较高行业价值的新闻。

优先：
- OpenAI、Google、Anthropic、Meta、xAI 等重要 AI 公司重大动态
- AI Agent
- 大模型
- AI 安全
- AI 科研突破
- AI 产品重大变化
- AI 行业重大事件
- 对 AI 行业可能产生明显影响的事件

三、严格排除：
- AI 只是顺带提到
- 普通网络安全事件
- 普通企业裁员
- 普通商业新闻
- 普通软件更新
- 普通芯片新闻
- 普通机器人新闻
- 普通云计算新闻
- 新闻简报
- Newsletter
- Roundup
- The Download
- “and more”
- 一篇文章包含大量互不相关事件的综合文章

四、不要为了凑够 5 条而降低标准。

宁可只选 1～3 条真正重要的 AI 新闻，
也不要选择质量一般的新闻。

五、判断必须基于提供的标题和摘要。

绝对不能因为你“知道”某个事件，
就自行补充没有出现在材料中的事实。

六、相同事件的不同报道必须归为同一个 duplicate_group。

七、score 规则：

9-10：重大 AI 行业事件
8：重要 AI 新闻
7：有一定行业价值
6 以下：不要选择

【必须返回 JSON】

只返回 JSON 数组。

不要返回 Markdown。
不要返回解释文字。

格式：

[
  {{
    "index": 1,
    "is_ai": true,
    "is_major": true,
    "duplicate_group": "事件名称",
    "score": 9,
    "reason": "简短说明为什么值得关注"
  }}
]

新闻：

{news_context}
"""

    result = call_ai(prompt, max_tokens=1800)

    # 去掉可能存在的 Markdown
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
        data = json.loads(result)

        print("\n========== AI 原始筛选结果 ==========\n")
        print(json.dumps(
            data,
            ensure_ascii=False,
            indent=2
        ))

        return data

    except Exception as e:

        print("\nAI 返回的 JSON 解析失败：")
        print(result)

        raise RuntimeError(
            f"AI 筛选结果无法解析为 JSON：{e}"
        )


# ============================================================
# 程序二次过滤
# ============================================================

def filter_selected_news(selected_news, all_news):

    print("\n========== 程序二次过滤 ==========")

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

        title = all_news[index - 1]["title"]

        title_lower = title.lower()

        # ----------------------------------------------------
        # AI 必须为 true
        # ----------------------------------------------------

        if is_ai is not True:

            print(
                f"过滤：新闻 {index}，is_ai={is_ai}"
            )

            continue

        # ----------------------------------------------------
        # 必须达到重大/重要新闻标准
        # ----------------------------------------------------

        if is_major is not True:

            print(
                f"过滤：新闻 {index}，is_major={is_major}"
            )

            continue

        # ----------------------------------------------------
        # 分数最低 7
        # ----------------------------------------------------

        if score < 7:

            print(
                f"过滤：新闻 {index}，score={score}"
            )

            continue

        # ----------------------------------------------------
        # 过滤综合型文章
        # ----------------------------------------------------

        is_roundup = False

        for keyword in roundup_keywords:

            if keyword in title_lower:

                is_roundup = True

                break

        if is_roundup:

            print(
                f"过滤：新闻 {index}，疑似综合/简报文章：{title}"
            )

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
    # duplicate_group 去重
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

        index = item["index"]

        print(
            f"- 新闻 {index} | "
            f"score={item.get('score')} | "
            f"{all_news[index - 1]['title']}"
        )

    return unique_news


# ============================================================
# 生成公众号文章
# ============================================================

def generate_article(selected_news, all_news):

    if not selected_news:

        return (
            f"【今日AI资讯】\n\n"
            f"今天是{get_beijing_date()}，"
            f"暂无符合筛选标准的 AI 重大资讯。"
        )

    news_material = []

    for number, item in enumerate(selected_news, start=1):

        index = int(item["index"])

        news = all_news[index - 1]

        news_material.append(
            f"""
新闻编号：新闻{number}

来源：{news["source"]}

原标题：
{news["title"]}

发布时间：
{news["pub_date"]}

原始摘要：
{news["summary"]}

原文链接：
{news["link"]}
""".strip()
        )

    material = "\n\n====================\n\n".join(
        news_material
    )

    prompt = f"""
你是一名中文科技公众号编辑。

请根据下面提供的国外 AI 新闻原始材料，
写一篇适合微信公众号发布的中文 AI 新闻资讯文章。

今天日期：
{get_beijing_date()}

【极其重要：事实准确性规则】

你只能使用“原标题”和“原始摘要”中明确提供的信息。

绝对禁止：

1. 不得自行补充新闻材料中没有出现的人名。
2. 不得自行补充数字。
3. 不得自行补充时间。
4. 不得自行补充公司内部信息。
5. 不得自行补充采访内容。
6. 不得自行补充专家观点。
7. 不得自行补充技术细节。
8. 不得自行补充事件原因。
9. 不得自行补充事件后果。
10. 不得自行补充市场影响。
11. 不得自行补充“业内认为”。
12. 不得自行补充“这意味着”之类的推测性结论。
13. 不得把标题中的推测改写成已经确定的事实。
14. 不得根据你自己的知识补充背景事实。
15. 不得修改原新闻事实。

如果原始摘要信息很少，
就只写已经明确知道的内容。

宁可文章短一点，
也绝对不能编造事实。

【标题规则】

可以对原标题进行中文化改写，
但不能改变原意。

【正文规则】

每条新闻控制在 1～2 个自然段。

语言自然、简洁、像一个真正的中文科技公众号编辑。

避免明显的 AI 套话，例如：

“这意味着……”
“值得注意的是……”
“重新定义……”
“引发广泛关注……”
“在这一背景下……”
“这标志着……”
“未来值得期待……”

除非这些内容确实出现在原始新闻材料中，
否则不要使用。

【文章结构】

第一行：

【今日AI资讯】

第二行：

今天是{get_beijing_date()}，整理几条值得关注的 AI 资讯。

然后依次：

【新闻1】
中文标题

正文

【新闻2】
中文标题

正文

……

最后不要写总结。

不要写“总体来看”。

不要写“未来”。

不要写额外评论。

【特别重要】

不要输出来源。
不要输出原文链接。
不要输出 Markdown 链接。
不要输出 URL。

来源和 URL 会由程序自动添加。

【原始新闻材料】

{material}
"""

    print(
        "\n========== 开始生成公众号文章 ==========\n"
    )

    article = call_ai(
        prompt,
        max_tokens=1800
    )

    # --------------------------------------------------------
    # 清理 Markdown 代码围栏
    # --------------------------------------------------------

    article = article.strip()

    if article.startswith("```"):

        article = re.sub(
            r"^```(?:markdown|md|text)?",
            "",
            article,
            flags=re.IGNORECASE
        )

        article = re.sub(
            r"```$",
            "",
            article
        )

        article = article.strip()

    # --------------------------------------------------------
    # 删除 AI 可能自己生成的来源/URL
    # 程序之后会重新添加
    # --------------------------------------------------------

    article = re.sub(
        r"来源\s*[:：]\s*.*",
        "",
        article,
        flags=re.IGNORECASE
    )

    article = re.sub(
        r"原文\s*[:：]\s*.*",
        "",
        article,
        flags=re.IGNORECASE
    )

    # 删除 Markdown URL
    article = re.sub(
        r"\[https?://[^\]]+\]\([^)]+\)",
        "",
        article
    )

    # 删除裸 URL
    article = re.sub(
        r"https?://\S+",
        "",
        article
    )

    article = re.sub(
        r"\n{3,}",
        "\n\n",
        article
    ).strip()

    # --------------------------------------------------------
    # Python 自动添加来源和原文链接
    # --------------------------------------------------------

    source_parts = []

    for number, item in enumerate(selected_news, start=1):

        index = int(item["index"])

        news = all_news[index - 1]

        source_parts.append(
            f"""
【新闻{number}来源】

来源：{news["source"]}

原文：{news["link"]}
""".strip()
        )

    article += "\n\n\n" + "\n\n".join(
        source_parts
    )

    return article


# ============================================================
# 主程序
# ============================================================

def main():

    print("\n========================================")
    print("        AI 新闻自动化系统启动")
    print("========================================\n")

    # --------------------------------------------------------
    # 第一步：抓 RSS
    # --------------------------------------------------------

    all_news = []

    for source_name, rss_url in RSS_SOURCES.items():

        news = fetch_rss(
            source_name,
            rss_url
        )

        all_news.extend(news)

    if not all_news:

        raise RuntimeError(
            "没有抓取到任何新闻"
        )

    print(
        f"\n========== RSS 总新闻数：{len(all_news)} =========="
    )

    # --------------------------------------------------------
    # 第二步：AI 筛选
    # --------------------------------------------------------

    selected_news = ask_ai(
        all_news
    )

    # --------------------------------------------------------
    # 第三步：程序二次过滤
    # --------------------------------------------------------

    selected_news = filter_selected_news(
        selected_news,
        all_news
    )

    # --------------------------------------------------------
    # 第四步：生成公众号文章
    # --------------------------------------------------------

    article = generate_article(
        selected_news,
        all_news
    )

    # --------------------------------------------------------
    # 第五步：输出最终文章
    # --------------------------------------------------------

    print(
        "\n========== AI 公众号文章 ==========\n"
    )

    print(article)

    print(
        "\n========================================"
    )

    print("AI 新闻自动化流程执行完成")

    print(
        "========================================\n"
    )


if __name__ == "__main__":
    main()
