import urllib.request
import urllib.parse
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


def ask_ai(news):
    api_key = os.environ.get("SILICONFLOW_API_KEY")

    if not api_key:
        raise Exception("没有找到 SILICONFLOW_API_KEY")

    news_text = "\n".join(
        f"{i + 1}. [{item['source']}] {item['title']}"
        for i, item in enumerate(news)
    )

    prompt = f"""
你是一名专业的 AI 科技新闻编辑。

下面是今天抓取到的新闻：

{news_text}

请从中筛选出最值得中国科技读者关注的 AI 新闻。

筛选标准：
1. 必须与人工智能、AI 模型、AI 公司、AI 芯片或 AI 行业重大事件有关。
2. 优先选择影响行业较大的新闻。
3. 普通产品更新、小工具、广告宣传、重复新闻可以淘汰。
4. 最多选择 5 条。
5. 按重要性从高到低排序。

请严格按照下面格式输出：

1. 新闻标题
重要性：9/10
理由：一句话说明为什么值得报道

2. 新闻标题
重要性：8/10
理由：一句话说明为什么值得报道

不要输出其他内容。
"""

    payload = {
        "model": "Qwen/Qwen3-8B",
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
        "https://api.siliconflow.cn/v1/chat/completions",
        data=data,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        },
        method="POST"
    )

    with urllib.request.urlopen(request, timeout=120) as response:
        result = json.loads(response.read().decode("utf-8"))

    answer = result["choices"][0]["message"]["content"]

    print("\n========== AI 筛选结果 ==========\n")
    print(answer)

    return answer


if __name__ == "__main__":
    print("开始抓取 AI 新闻...")

    all_news = []

    for name, url in RSS_SOURCES.items():
        news = fetch_rss(name, url)
        all_news.extend(news)

    print(f"\n总共抓取 {len(all_news)} 条新闻")

    if all_news:
        ask_ai(all_news)
    else:
        print("没有抓到新闻，跳过 AI 筛选。")

    print("\nAI 新闻筛选任务完成！")
