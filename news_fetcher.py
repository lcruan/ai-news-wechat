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
    """让 AI 严格筛选 AI 新闻"""

    news_text = ""

    for index, news in enumerate(
        news_list,
        1
    ):

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
你是一名非常严格的中文 AI 科技新闻编辑。

下面是从科技媒体 RSS 获取的真实新闻资料。

你的任务不是“尽量多选”，而是：

从这些新闻中，只挑选真正值得作为
“AI新闻”发布的内容。

==================================================
一、什么才算 AI 新闻
==================================================

必须满足下面至少一项：

1. AI 模型、基础模型、LLM、多模态模型、
   AI Agent、生成式 AI 等重大更新。

2. AI 产品、AI 工具、AI 服务的重要发布或重大变化。

3. AI 公司或大型科技公司的重大 AI 动态。

4. AI 技术突破、重要研究成果。

5. AI 安全、AI 治理、AI 监管等重大事件。

6. AI 芯片、AI 算力、AI 数据中心等与 AI
   有直接关系的重要产业事件。

==================================================
二、以下情况不要选
==================================================

即使标题里面出现 AI，也不要选：

1. 普通网络安全新闻，只是顺便提到 AI。

2. 普通机器人新闻，除非文章明确说明
   与 AI 技术有直接重要关系。

3. 电池、汽车、硬件、商业等新闻，
   只是顺带提到 AI。

4. 一篇文章同时讨论多个完全不同主题，
   但 AI 只是其中一个小部分。

5. 普通产品更新、普通融资、普通公司新闻，
   如果没有明显新闻价值，不要选。

6. 不能从提供的标题和摘要确认
   AI 是核心主题的新闻，不要选。

==================================================
三、新闻价值
==================================================

优先选择：

9-10分：
重大 AI 公司、重大模型、重大技术突破、
重大安全事件、重大行业事件。

7-8分：
明显具有行业影响力的重要 AI 新闻。

5-6分：
有一定价值，但不是重大事件。

低于 5 分：
不要选择。

==================================================
四、重复新闻处理
==================================================

如果多篇新闻实际上讲的是同一个事件：

只保留最值得关注的一篇。

例如：

新闻A：OpenAI宣布数学研究突破

新闻B：OpenAI数学突破引发争议

如果它们明显属于同一个事件，
不要同时选择。

但如果两篇文章确实是不同事件，
可以分别选择。

==================================================
五、非常重要
==================================================

宁可只选择 2 条、3 条，
也不要为了凑够 5 条而选择质量一般的新闻。

最多选择 5 条。

==================================================
六、事实限制
==================================================

只能根据下面提供的：

- 标题
- 摘要
- 来源
- 发布时间
- 原文链接

判断新闻。

绝对禁止：

- 根据自己的知识补充事实
- 根据标题猜测文章内容
- 编造人物
- 编造公司
- 编造数字
- 编造时间
- 编造事件经过
- 编造研究结果
- 编造新闻背景

如果标题和摘要不足以确认，
就不要选。

==================================================
七、输出格式
==================================================

只输出 JSON 数组。

不要输出 Markdown。

不要输出解释。

格式：

[
  {{
    "index": 1,
    "is_ai": true,
    "is_major": true,
    "duplicate_group": "openai-agent-security",
    "score": 9,
    "reason": "AI安全事件，AI是新闻核心，具有较高行业关注价值"
  }}
]

字段说明：

index：
新闻编号。

is_ai：
是否真正属于 AI 新闻。

is_major：
是否具有足够新闻价值。

duplicate_group：
如果属于同一事件，使用相同的英文分组名称。
如果没有明显重复事件，可以使用新闻自己的唯一分组名称。

score：
新闻价值，1-10。

reason：
用一句话说明为什么选择。

==================================================
新闻资料
==================================================

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

==================================================
写作要求
==================================================

1. 使用简体中文。

2. 语言自然、简洁，像真实科技媒体编辑。

3. 不要有明显的 AI 生成腔。

4. 不要频繁使用：

“这意味着”
“值得注意的是”
“重新定义”
“再次证明”
“引发广泛关注”
“正在重塑”
“未来可期”

等空泛套话。

5. 开头用 2-3 句话概括今天的 AI 动态。

6. 每条新闻单独介绍。

7. 每条新闻包含：

- 一个自然的小标题
- 发生了什么
- 为什么值得关注

8. 内容以新闻资料为准。

9. 不要夸大新闻。

10. 不要把推测写成事实。

11. 不要给新闻资料之外的信息。

12. 如果摘要信息不足，
    就简短介绍，不要自行扩写。

13. 每条新闻末尾注明来源。

格式：

来源：Ars Technica
原文：新闻原文链接

==================================================
最重要的事实规则
==================================================

你只能使用我提供的：

- 来源
- 标题
- 摘要
- 发布时间
- 原文链接

禁止使用你自己的知识补充新闻。

禁止：

- 编造人物
- 编造数字
- 编造时间
- 编造产品
- 编造公司
- 编造事件经过
- 编造研究结果
- 编造不存在的背景

如果资料没有说，
就不要写。

==================================================
新闻资料
==================================================

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
