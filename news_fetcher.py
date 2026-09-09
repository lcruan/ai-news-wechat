import os
import json
import urllib.request
import xml.etree.ElementTree as ET
from html import unescape
import re
import time


RSS_SOURCES = {
    "Ars Technica": "https://feeds.arstechnica.com/arstechnica/technology-lab",
    "MIT Technology Review": "https://www.technologyreview.com/feed/",
}

API_URL = "https://api.siliconflow.cn/v1/chat/completions"
MODEL = "Qwen/Qwen3-8B"


def clean_text(text):
    """清理 HTML 标签和多余空白"""
    if not text:
        return ""

    text = unescape(text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)

    return text.strip()


def fetch_rss(source_name, url):
    """获取 RSS 新闻"""

    print(f"\n正在抓取：{source_name}")

    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0"
            }
        )

        # RSS 请求保持 120 秒
        with urllib.request.urlopen(req, timeout=120) as response:
            data = response.read()

        root = ET.fromstring(data)

        news_list = []

        # =========================
        # RSS 格式
        # =========================

        for item in root.findall(".//item"):

            title = item.findtext("title", "")
            summary = item.findtext("description", "")
            link = item.findtext("link", "")
            pub_date = item.findtext("pubDate", "")

            if not title:
                continue

            news_list.append({
                "source": source_name,
                "title": clean_text(title),
                "summary": clean_text(summary)[:1500],
                "link": link.strip(),
                "pub_date": pub_date.strip(),
            })

        # =========================
        # Atom 格式
        # =========================

        if not news_list:

            ns = {
                "atom": "http://www.w3.org/2005/Atom"
            }

            for entry in root.findall(".//atom:entry", ns):

                title = entry.findtext(
                    "atom:title",
                    "",
                    ns
                )

                summary = entry.findtext(
                    "atom:summary",
                    "",
                    ns
                )

                updated = entry.findtext(
                    "atom:updated",
                    "",
                    ns
                )

                published = entry.findtext(
                    "atom:published",
                    "",
                    ns
                )

                link = ""

                link_element = entry.find(
                    "atom:link",
                    ns
                )

                if link_element is not None:
                    link = link_element.attrib.get(
                        "href",
                        ""
                    )

                if not title:
                    continue

                news_list.append({
                    "source": source_name,
                    "title": clean_text(title),
                    "summary": clean_text(summary)[:1500],
                    "link": link.strip(),
                    "pub_date": (
                        published.strip()
                        if published
                        else updated.strip()
                    ),
                })

        print(
            f"{source_name} 获取 {len(news_list)} 条新闻"
        )

        # 每个新闻源最多取 10 条
        return news_list[:10]

    except Exception as e:

        print(
            f"{source_name} 抓取失败：{e}"
        )

        return []


def call_ai(prompt):
    """调用 SiliconFlow，失败后自动重试"""

    api_key = os.environ.get(
        "SILICONFLOW_API_KEY"
    )

    if not api_key:
        raise RuntimeError(
            "没有找到 SILICONFLOW_API_KEY"
        )

    payload = {
        "model": MODEL,
        "messages": [
            {
                "role": "user",
                "content": prompt
            }
        ],

        # 降低随机性，减少胡编乱造
        "temperature": 0.2,

        # 限制输出长度
        "max_tokens": 1800
    }

    data = json.dumps(
        payload,
        ensure_ascii=False
    ).encode("utf-8")

    # 最多尝试 3 次
    for attempt in range(1, 4):

        try:

            print(
                f"\n正在调用 SiliconFlow，"
                f"第 {attempt}/3 次..."
            )

            request = urllib.request.Request(
                API_URL,
                data=data,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": (
                        f"Bearer {api_key}"
                    )
                },
                method="POST"
            )

            # SiliconFlow 请求保持 120 秒
            with urllib.request.urlopen(
                request,
                timeout=120
            ) as response:

                result = json.loads(
                    response.read().decode("utf-8")
                )

            print(
                "SiliconFlow 调用成功"
            )

            return result["choices"][0]["message"]["content"]

        except Exception as e:

            print(
                f"第 {attempt} 次调用失败：{e}"
            )

            if attempt == 3:
                raise

            print(
                "等待 5 秒后重试..."
            )

            time.sleep(5)


def ask_ai(news_list):
    """让 AI 筛选真正重要的 AI 新闻"""

    news_text = ""

    for index, news in enumerate(
        news_list,
        1
    ):

        news_text += f"""

【新闻 {index}】
来源：{news["source"]}
标题：{news["title"]}
摘要：{news["summary"]}
发布时间：{news["pub_date"]}
原文链接：{news["link"]}
"""

    prompt = f"""
你是一名专业的 AI 科技新闻编辑。

下面是从科技媒体 RSS 获取的真实新闻信息。

你的任务是：
从中筛选真正与人工智能相关、
并且具有新闻价值的内容。

筛选标准：

1. 必须是真正的 AI 新闻。
2. 优先选择重大 AI 模型、产品、
   技术突破、公司动态和行业事件。
3. 优先选择 OpenAI、Google、
   Anthropic、Meta、Microsoft、
   NVIDIA、DeepSeek、阿里、
   腾讯、字节等重要 AI 动态。
4. 明显与 AI 无关的新闻必须排除。
5. 不要为了凑数量而选择无关新闻。
6. 最多选择 5 条。
7. 如果只有 2 条符合，
   就只选择 2 条。
8. 新闻价值不足的内容不要选择。

【非常重要】

只能根据下面提供的：

- 标题
- 摘要
- 来源
- 发布时间
- 原文链接

进行判断。

禁止根据自己的知识补充新闻事实。

不要猜测新闻内容。

请输出 JSON 数组，
不要输出其他文字。

格式：

[
  {{
    "index": 1,
    "score": 9,
    "reason": "为什么值得关注"
  }}
]

新闻资料：

{news_text}
"""

    result = call_ai(prompt)

    print("\n========== AI 筛选结果 ==========")
    print(result)

    return result


def generate_article(selected_news, all_news):
    """根据真实新闻信息生成公众号文章"""

    news_text = ""

    for item in selected_news:

        index = item["index"]

        # 防止 AI 返回非法 index
        if (
            not isinstance(index, int)
            or index < 1
            or index > len(all_news)
        ):
            continue

        news = all_news[index - 1]

        news_text += f"""

【新闻 {index}】

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
"""

    prompt = f"""
你是一名中文科技公众号编辑。

请根据下面提供的真实新闻资料，
写一篇适合微信公众号发布的
AI 科技新闻文章。

文章要求：

1. 使用简体中文。
2. 语言自然，像真实科技编辑。
3. 不要有明显的 AI 生成腔。
4. 不要频繁使用：
   “这意味着”
   “值得注意的是”
   “重新定义”
   等套话。
5. 开头简单介绍今天值得关注的
   AI 行业动态。
6. 每条新闻单独介绍。
7. 每条新闻包含：
   - 新闻标题
   - 发生了什么
   - 为什么值得关注
8. 最后进行简短总结。
9. 不要故意夸张。
10. 不要编造任何事实。

【最重要的规则】

你只能使用我提供的新闻资料。

禁止：

- 根据标题猜测新闻细节
- 使用自己记忆中的新闻补充内容
- 编造人物
- 编造公司
- 编造产品
- 编造数字
- 编造时间
- 编造事件经过
- 添加资料中不存在的事实

如果资料中没有相关信息，
就不要写。

不要把推测写成事实。

如果摘要信息不足，
宁可少写，也不要脑补。

每条新闻最后保留原文链接。

文章资料：

{news_text}
"""

    article = call_ai(prompt)

    return article


def main():

    print(
        "========== AI 新闻自动化开始 =========="
    )

    all_news = []

    # =========================
    # 1. 抓取 RSS
    # =========================

    for source_name, url in RSS_SOURCES.items():

        news = fetch_rss(
            source_name,
            url
        )

        all_news.extend(news)

    print(
        f"\n总共获取 {len(all_news)} 条新闻"
    )

    if not all_news:

        print(
            "没有获取到新闻"
        )

        return

    # =========================
    # 2. AI 筛选
    # =========================

    selected_result = ask_ai(
        all_news
    )

    try:

        selected_news = json.loads(
            selected_result
        )

    except Exception as e:

        print(
            "\nAI 返回的 JSON 解析失败：",
            e
        )

        print(
            selected_result
        )

        return

    if not selected_news:

        print(
            "今天没有筛选出符合条件的 AI 新闻"
        )

        return

    # =========================
    # 3. AI 生成公众号文章
    # =========================

    print(
        "\n========== 开始生成公众号文章 =========="
    )

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


if __name__ == "__main__":
    main()
