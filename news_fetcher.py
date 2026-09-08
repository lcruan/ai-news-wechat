import urllib.request
import xml.etree.ElementTree as ET
import json
import os


RSS_SOURCES = {
    "Ars Technica": "https://feeds.arstechnica.com/arstechnica/technology-lab",
    "MIT Technology Review": "https://www.technologyreview.com/feed/",
}


def fetch_rss(name, url):
    print(f"\n========== {name} ==========")

    try:
        request = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0"}
        )

        with urllib.request.urlopen(request, timeout=20) as response:
            data = response.read()

        root = ET.fromstring(data)

        items = root.findall(".//item")

        if not items:
            items = root.findall(
                ".//{http://www.w3.org/2005/Atom}entry"
            )

        news = []

        for item in items:
            title = item.find("title")

            if title is None:
                title = item.find(
                    "{http://www.w3.org/2005/Atom}title"
                )

            if title is None or not title.text:
                continue

            news.append({
                "source": name,
                "title": title.text.strip()
            })

            if len(news) >= 10:
                break

        print(f"成功获取 {len(news)} 条新闻")

        return news

    except Exception as e:
        print(f"抓取失败：{e}")
        return []


def call_ai(prompt):
    api_key = os.environ.get("SILICONFLOW_API_KEY")

    if not api_key:
        raise Exception("没有找到 SILICONFLOW_API_KEY")

    payload = {
        "model": "Qwen/Qwen3-8B",
        "messages": [
            {
                "role": "user",
                "content": prompt
            }
        ],
        "temperature": 0.3
    }

    data = json.dumps(payload).encode("utf-8")

    request = urllib.request.Request(
        "https://api.siliconflow.cn/v1/chat/completions",
        data=data,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        },
        method="POST"
    )

    with urllib.request.urlopen(request, timeout=120) as response:
        result = json.loads(
            response.read().decode("utf-8")
        )

    return result["choices"][0]["message"]["content"]


def ask_ai(news):
    news_text = "\n".join(
        f"{i + 1}. [{item['source']}] {item['title']}"
        for i, item in enumerate(news)
    )

    prompt = f"""
你是一名专业的 AI 科技新闻编辑。

下面是今天抓取到的国外科技新闻：

{news_text}

请从中筛选最值得中国科技读者关注的 AI 新闻。

要求：

1. 只选择真正与人工智能密切相关的新闻。
2. AI 模型、AI Agent、AI 公司、AI 芯片、机器人、生成式 AI 等优先。
3. 普通网络安全、普通科技新闻，如果和 AI 没有直接关系，不要选择。
4. 最多选择 5 条。
5. 按重要性从高到低排序。
6. 不要为了凑够 5 条而选择无关新闻。

严格按照下面格式输出：

1. 新闻标题
重要性：9/10
理由：一句话说明为什么值得关注

2. 新闻标题
重要性：8/10
理由：一句话说明为什么值得关注
"""

    result = call_ai(prompt)

    print("\n========== AI 筛选结果 ==========\n")
    print(result)

    return result


def generate_article(selected_news):
    prompt = f"""
你是一名优秀的中文科技公众号主编。

下面是今天筛选出来的 AI 重大新闻：

{selected_news}

请根据这些新闻，写一篇适合微信公众号发布的中文科技文章。

文章要求：

【整体风格】
- 面向普通科技爱好者和程序员
- 中文表达自然、通俗、有信息量
- 不要写得像机器生成的新闻摘要
- 可以适当加入你的分析和观点
- 不要夸张标题党
- 不要编造新闻中没有出现的事实

【文章结构】

第一部分：标题

生成一个吸引人的中文标题。

第二部分：开头导语

用 2～3 段话介绍今天 AI 圈最值得关注的变化。

第三部分：新闻正文

按照重要性依次介绍每条新闻。

每条新闻使用：

### 1. 新闻标题

然后写：

发生了什么？

为什么重要？

对 AI 行业有什么影响？

普通人/程序员应该关注什么？

每条新闻大约 300～500 字。

第四部分：今日总结

用 2～3 段话总结今天 AI 行业最值得关注的趋势。

第五部分：结尾

写一段适合微信公众号的结语，引导读者关注后续 AI 发展。

【重要】
- 全文使用简体中文。
- 不要使用 Markdown 表格。
- 不要输出“以下是文章”“好的”等无关内容。
- 直接输出完整文章。
- 不要虚构具体数据、人物言论或事件细节。
"""

    article = call_ai(prompt)

    print("\n\n")
    print("=" * 60)
    print("========== AI 公众号文章 ==========")
    print("=" * 60)
    print("\n")

    print(article)

    print("\n")
    print("=" * 60)
    print("========== 文章生成完成 ==========")
    print("=" * 60)

    return article


if __name__ == "__main__":
    print("开始抓取 AI 新闻...")

    all_news = []

    for name, url in RSS_SOURCES.items():
        news = fetch_rss(name, url)
        all_news.extend(news)

    print(f"\n总共抓取 {len(all_news)} 条新闻")

    if all_news:

        # 第一步：AI筛选新闻
        selected_news = ask_ai(all_news)

        # 第二步：AI生成公众号文章
        generate_article(selected_news)

    else:
        print("没有抓到新闻，跳过 AI 筛选。")

    print("\nAI 新闻自动化任务完成！")
