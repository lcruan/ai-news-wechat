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

        # 降低随机性
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

下面是从科技媒体 RSS 获取的真实新闻。

你的任务是筛选真正值得发布为
“AI新闻”的内容。

==================================================
一、最重要的判断标准
==================================================

请先问自己：

“如果把 AI 两个字从这篇新闻里删除，
这篇新闻还成立吗？”

如果答案是“是”，并且 AI 只是顺带提到，
那么：

is_ai = false

例如：

微软发布大量普通安全补丁，
只是因为 AI 可能增加攻击风险而提到 AI。

这种新闻不是 AI 核心新闻。

又例如：

VMware、云计算、企业软件、
商业策略等新闻只是顺带提到 AI。

也不要选择。

==================================================
二、真正可以选择的 AI 新闻
==================================================

优先选择：

1. AI 模型重大更新。

2. LLM、生成式 AI、多模态 AI
   等重大技术进展。

3. AI Agent 重大进展。

4. AI 公司重大产品或战略变化。

5. AI 安全重大事件。

6. AI 研究重大突破。

7. AI 芯片、AI 算力、AI 数据中心等
   明确以 AI 为核心的重大产业新闻。

8. AI 监管、治理等重大事件。

==================================================
三、严格排除
==================================================

以下内容不要选择：

1. 普通网络安全新闻。

2. 普通软件新闻。

3. 普通云计算新闻。

4. 普通机器人新闻。

5. 普通硬件新闻。

6. 普通商业新闻。

7. 普通企业新闻。

8. 电池、汽车、芯片等新闻只是顺带提到 AI。

9. AI 只是文章背景，而不是新闻核心。

10. 无法通过标题和摘要确认 AI 是核心主题。

==================================================
四、新闻价值
==================================================

score 只能根据提供的新闻资料判断。

9-10：
重大 AI 事件。

7-8：
明显具有行业价值的重要 AI 新闻。

低于 7：
不要选择。

==================================================
五、重复新闻
==================================================

如果多篇新闻实际上讲的是同一个事件：

只保留最重要的一篇。

例如：

A：OpenAI宣布数学研究突破

B：OpenAI数学突破引发争议

如果明显是同一个事件，
不要同时选择。

==================================================
六、事实限制
==================================================

只能根据：

- 标题
- 摘要
- 来源
- 发布时间
- 原文链接

进行判断。

禁止：

- 使用自己的知识补充
- 猜测文章内容
- 编造事实
- 编造数字
- 编造人物
- 编造公司
- 编造时间
- 编造事件经过

==================================================
七、输出格式
==================================================

只输出 JSON 数组。

不要输出 Markdown。

不要输出其他文字。

格式：

[
  {{
    "index": 1,
    "is_ai": true,
    "is_major": true,
    "duplicate_group": "unique-event-1",
    "score": 9,
    "reason": "AI是新闻核心，并且具有较高新闻价值"
  }}
]

字段：

index：
新闻编号。

is_ai：
AI是否为新闻核心主题。

is_major：
是否具有足够新闻价值。

duplicate_group：
同一事件使用相同名称。
不同事件使用不同名称。

score：
新闻价值，1-10。

reason：
一句话说明判断原因。

==================================================
新闻资料
==================================================

{news_text}
"""

    result = call_ai(prompt)

    print("\n========== AI 原始筛选结果 ==========")
    print(result)

    return result


def filter_selected_news(selected_news, all_news):
    """
    程序再次过滤 AI 结果。

    不完全相信 AI，
    由程序执行第二层保险。
    """

    print("\n========== 程序二次过滤 ==========")

    valid_news = []

    for item in selected_news:

        try:
            index = int(item.get("index", 0))
        except Exception:
            continue

        is_ai = item.get("is_ai", False)
        is_major = item.get("is_major", False)

        try:
            score = int(item.get("score", 0))
        except Exception:
            score = 0

        # -------------------------
        # 1. index 必须合法
        # -------------------------

        if index < 1 or index > len(all_news):

            print(
                f"过滤：新闻 {index}，index 无效"
            )

            continue

        # -------------------------
        # 2. 必须是真正 AI 新闻
        # -------------------------

        if is_ai is not True:

            print(
                f"过滤：新闻 {index}，"
                f"is_ai={is_ai}"
            )

            continue

        # -------------------------
        # 3. 必须有足够新闻价值
        # -------------------------

        if is_major is not True:

            print(
                f"过滤：新闻 {index}，"
                f"is_major={is_major}"
            )

            continue

        # -------------------------
        # 4. 分数至少 7
        # -------------------------

        if score < 7:

            print(
                f"过滤：新闻 {index}，"
                f"score={score}"
            )

            continue

        valid_news.append(item)

    # =========================
    # 按分数从高到低排序
    # =========================

    valid_news.sort(
        key=lambda x: int(x.get("score", 0)),
        reverse=True
    )

    # =========================
    # 同一事件去重
    # =========================

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
            group = f"news-{item['index']}"

        if group in duplicate_groups:

            print(
                f"过滤：新闻 {item['index']}，"
                f"与其他新闻属于同一事件：{group}"
            )

            continue

        duplicate_groups.add(group)

        unique_news.append(item)

    # =========================
    # 最多保留 5 条
    # =========================

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


def generate_article(selected_news, all_news):
    """根据真实新闻信息生成公众号文章"""

    news_text = ""

    for item in selected_news:

        index = item["index"]

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

2. 语言自然、简洁。

3. 像真实科技媒体编辑，
   不要有明显 AI 生成腔。

4. 不要频繁使用：

“这意味着”
“值得注意的是”
“重新定义”
“再次证明”
“正在重塑”
“未来可期”

等套话。

5. 开头用 2-3 句话概括今天的 AI 动态。

6. 每条新闻单独介绍。

7. 每条新闻包含：

- 新闻标题
- 发生了什么
- 为什么值得关注

8. 新闻标题可以稍微润色，
   但不能改变原始事实。

9. 不要夸张。

10. 不要把推测写成事实。

11. 不要添加资料中不存在的信息。

12. 如果摘要信息不足，
    就少写。

==================================================
事实安全规则
==================================================

只能使用我提供的：

- 来源
- 标题
- 摘要
- 发布时间
- 原文链接

禁止：

- 使用你自己的知识补充
- 根据标题猜测细节
- 编造人物
- 编造数字
- 编造时间
- 编造产品
- 编造公司
- 编造事件经过
- 编造研究结果
- 编造背景

如果资料没有明确说明，
不要写。

==================================================
来源格式
==================================================

每条新闻最后写：

来源：XXX

原文：
XXX

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
    # 2. AI 初步筛选
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
            "AI 没有筛选出新闻"
        )

        return

    # =========================
    # 3. 程序二次过滤
    # =========================

    selected_news = filter_selected_news(
        selected_news,
        all_news
    )

    if not selected_news:

        print(
            "\n经过严格过滤后，"
            "今天没有符合要求的 AI 新闻。"
        )

        return

    # =========================
    # 4. AI 生成文章
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
