import os
import json
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from html import unescape


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

    import re
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

        with urllib.request.urlopen(req, timeout=120) as response:
            data = response.read()

        root = ET.fromstring(data)

        news_list = []

        # RSS 格式
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

        # Atom 格式
        if not news_list:
            ns = {
                "atom": "http://www.w3.org/2005/Atom"
            }

            for entry in root.findall(".//atom:entry", ns):
                title = entry.findtext("atom:title", "", ns)
                summary = entry.findtext("atom:summary", "", ns)
                updated = entry.findtext("atom:updated", "", ns)
                published = entry.findtext("atom:published", "", ns)

                link = ""

                link_element = entry.find("atom:link", ns)

                if link_element is not None:
                    link = link_element.attrib.get("href", "")

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

        print(f"{source_name} 获取 {len(news_list)} 条新闻")

        return news_list[:10]

    except Exception as e:
        print(f"{source_name} 抓取失败：{e}")
        return []


def call_ai(prompt):
    """调用 SiliconFlow"""
    api_key = os.environ.get("SILICONFLOW_API_KEY")

    if not api_key:
        raise RuntimeError("没有找到 SILICONFLOW_API_KEY")

    payload = {
        "model": MODEL,
        "messages": [
            {
                "role": "user",
                "content": prompt
            }
        ],
        "temperature": 0.2
    }

    data = json.dumps(payload).encode("utf-8")

    request = urllib.request.Request(
        API_URL,
        data=data,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        },
        method="POST"
    )

    with urllib.request.urlopen(request, timeout=120) as response:
        result = json.loads(response.read().decode("utf-8"))

    return result["choices"][0]["message"]["content"]


def ask_ai(news_list):
    """让 AI 筛选真正重要的 AI 新闻"""

    news_text = ""

    for index, news in enumerate(news_list, 1):
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
从中筛选真正与人工智能相关、且具有新闻价值的内容。

筛选标准：
1. 必须是真正的 AI 新闻。
2. 优先选择 OpenAI、Google、Anthropic、Meta、Microsoft、NVIDIA、DeepSeek、阿里、腾讯、字节等公司的重要 AI 动态。
3. 优先选择新模型、新产品、重大融资、重要技术突破、重大行业事件。
4. 明显与 AI 无关的新闻必须排除。
5. 不要为了凑数量而选择无关新闻。
6. 最多选择 5 条。
7. 如果只有 2 条符合，就只选择 2 条。
8. 严禁根据标题自行猜测新闻内容。

非常重要：
只能根据下面提供的“标题、摘要、来源、时间、链接”判断。
不要使用你自己的知识补充新闻事实。

请输出 JSON 数组，不要输出其他内容。

格式：

[
  {{
    "index": 1,
    "score": 9,
    "reason": "为什么值得关注"
  }}
]

新闻：

{news_text}
"""

    result = call_ai(prompt)

    print("\nAI 筛选结果：")
    print(result)

    return result


def generate_article(selected_news, all_news):
    """根据真实新闻信息生成公众号文章"""

    news_text = ""

    for item in selected_news:
        index = item["index"]

        news = all_news[index - 1]

        news_text += f"""
【新闻】
来源：{news["source"]}
标题：{news["title"]}
摘要：{news["summary"]}
发布时间：{news["pub_date"]}
原文链接：{news["link"]}
"""

    prompt = f"""
你是一名中文科技公众号编辑。

请根据下面提供的真实新闻资料，写一篇适合微信公众号发布的 AI 科技新闻文章。

文章要求：

1. 使用简体中文。
2. 语言自然、像一个真实科技编辑写的文章。
3. 不要有明显的 AI 生成腔。
4. 不要频繁使用“这意味着”“值得注意的是”“重新定义”等套话。
5. 开头简单介绍今天 AI 行业值得关注的动态。
6. 每条新闻单独介绍。
7. 每条新闻包含：
   - 新闻标题
   - 发生了什么
   - 为什么值得关注
8. 最后进行一个简短总结。
9. 不需要故意写得特别夸张。
10. 不要编造任何事实。

【最重要的规则】

你只能使用我提供的新闻资料。

禁止：
- 根据标题猜测新闻细节
- 使用你自己记忆中的相关新闻补充内容
- 编造人物、公司、产品、数字、时间、事件经过
- 添加新闻资料中没有出现的事实

如果资料中没有某项信息，就不要写。

新闻中的链接必须保留。

文章最后不要添加“以上内容由 AI 生成”之类的话。

新闻资料：

{news_text}
"""

    article = call_ai(prompt)

    return article


def main():
    print("========== AI 新闻自动化开始 ==========")

    all_news = []

    # 1. 抓取 RSS
    for source_name, url in RSS_SOURCES.items():
        news = fetch_rss(source_name, url)
        all_news.extend(news)

    print(f"\n总共获取 {len(all_news)} 条新闻")

    if not all_news:
        print("没有获取到新闻")
        return

    # 2. AI 筛选
    selected_result = ask_ai(all_news)

    try:
        selected_news = json.loads(selected_result)
    except Exception as e:
        print("AI 返回的 JSON 解析失败：", e)
        print(selected_result)
        return

    if not selected_news:
        print("今天没有筛选出符合条件的 AI 新闻")
        return

    # 3. 生成文章
    article = generate_article(selected_news, all_news)

    print("\n========== AI 公众号文章 ==========\n")
    print(article)

    print("\n========== 任务完成 ==========")


if __name__ == "__main__":
    main()
