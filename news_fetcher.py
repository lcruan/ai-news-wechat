import os
import re
import json
import time
import html
import urllib.request
import urllib.error
import urllib.parse
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from datetime import datetime, timezone, timedelta


# ============================================================
# 基础配置
# ============================================================

SILICONFLOW_API_KEY = os.environ.get("SILICONFLOW_API_KEY")

SILICONFLOW_URL = "https://api.siliconflow.cn/v1/chat/completions"
MODEL = "Qwen/Qwen3-8B"

REQUEST_TIMEOUT = 120
MAX_RETRIES = 3
RETRY_WAIT_SECONDS = 5

ARTICLE_FILE = "article.json"
COVER_FILE = "cover.jpg"

# Medium 官方 Topic RSS
MEDIUM_FEEDS = [
    ("Medium Frontend Development", "https://medium.com/feed/tag/frontend-development"),
    ("Medium Web Development", "https://medium.com/feed/tag/web-development"),
    ("Medium Artificial Intelligence", "https://medium.com/feed/tag/artificial-intelligence"),
]

# DEV.to 官方 API
DEV_API_BASE = "https://dev.to/api"

# DEV.to 重点关注的标签
DEV_TAGS = [
    "frontend",
    "webdev",
    "javascript",
    "react",
    "vue",
    "ai",
]

# 每个来源最多读取多少篇
MAX_ITEMS_PER_SOURCE = 12

# 最终交给 AI 筛选的候选文章数量
MAX_CANDIDATES_FOR_AI = 20

# 单篇正文最大字符数
MAX_ARTICLE_CHARS = 18000

# 选题上下文最大字符数
MAX_SCREENING_CONTEXT_CHARS = 30000

# 最终文章每个 section 最大字符
MAX_SECTION_CHARS = 1800


# ============================================================
# 文本清理
# ============================================================

def clean_text(text):
    if not text:
        return ""

    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def strip_html(text):
    if not text:
        return ""

    text = re.sub(r"(?is)<script.*?>.*?</script>", " ", text)
    text = re.sub(r"(?is)<style.*?>.*?</style>", " ", text)
    text = re.sub(r"(?is)<[^>]+>", " ", text)

    return clean_text(text)


def normalize_url(url):
    if not url:
        return ""

    return html.unescape(url).strip()


def truncate_text(text, max_chars):
    text = text or ""

    if len(text) <= max_chars:
        return text

    return text[:max_chars] + "\n[正文已截断，仅用于模型处理]"


# ============================================================
# HTTP
# ============================================================

def http_get(url, headers=None, timeout=REQUEST_TIMEOUT):
    request_headers = {
        "User-Agent": (
            "Mozilla/5.0 "
            "(Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 "
            "(KHTML, like Gecko) "
            "Chrome/150.0 Safari/537.36"
        )
    }

    if headers:
        request_headers.update(headers)

    request = urllib.request.Request(
        url,
        headers=request_headers,
        method="GET"
    )

    with urllib.request.urlopen(
        request,
        timeout=timeout
    ) as response:
        return response.read()


def http_json_get(url, headers=None, timeout=REQUEST_TIMEOUT):
    data = http_get(
        url,
        headers=headers,
        timeout=timeout
    )

    return json.loads(
        data.decode("utf-8", errors="replace")
    )


# ============================================================
# HTML 内容解析
# ============================================================

class ArticleHTMLParser(HTMLParser):
    """
    不依赖第三方库的 HTML 解析器。

    目标：
    1. 提取正文文字
    2. 提取图片
    3. 忽略 script/style/nav/footer 等明显非正文区域
    """

    IGNORE_TAGS = {
        "script",
        "style",
        "noscript",
        "svg",
        "nav",
        "footer",
        "form",
        "button",
    }

    BLOCK_TAGS = {
        "p",
        "div",
        "section",
        "article",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "li",
        "blockquote",
        "pre",
        "br",
        "hr",
    }

    def __init__(self):
        super().__init__(
            convert_charrefs=True
        )

        self.text_parts = []
        self.images = []

        self.ignore_depth = 0
        self.current_tag_stack = []

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()

        attrs_dict = dict(attrs)

        if tag in self.IGNORE_TAGS:
            self.ignore_depth += 1
            return

        if self.ignore_depth > 0:
            return

        self.current_tag_stack.append(tag)

        if tag == "img":
            image_url = (
                attrs_dict.get("src")
                or attrs_dict.get("data-src")
                or attrs_dict.get("data-original")
                or ""
            )

            if not image_url:
                srcset = attrs_dict.get("srcset", "")

                if srcset:
                    first = srcset.split(",")[0].strip()

                    if first:
                        image_url = first.split(" ")[0]

            if image_url:
                self.images.append(
                    normalize_url(image_url)
                )

        if tag in self.BLOCK_TAGS:
            self.text_parts.append("\n")

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)

        if tag.lower() in self.BLOCK_TAGS:
            self.text_parts.append("\n")

    def handle_endtag(self, tag):
        tag = tag.lower()

        if tag in self.IGNORE_TAGS:
            if self.ignore_depth > 0:
                self.ignore_depth -= 1
            return

        if self.ignore_depth > 0:
            return

        if self.current_tag_stack:
            try:
                index = len(self.current_tag_stack) - 1 - self.current_tag_stack[::-1].index(tag)
                self.current_tag_stack.pop(index)
            except ValueError:
                pass

        if tag in self.BLOCK_TAGS:
            self.text_parts.append("\n")

    def handle_data(self, data):
        if self.ignore_depth > 0:
            return

        if not data:
            return

        text = clean_text(data)

        if text:
            self.text_parts.append(text)


def parse_html_content(content):
    parser = ArticleHTMLParser()

    try:
        parser.feed(content or "")
        parser.close()
    except Exception as e:
        print(f"HTML 解析出现异常：{e}")

    text = "\n".join(parser.text_parts)

    text = re.sub(
        r"\n{3,}",
        "\n\n",
        text
    )

    text = re.sub(
        r"[ \t]+\n",
        "\n",
        text
    )

    text = re.sub(
        r"\n[ \t]+",
        "\n",
        text
    )

    text = text.strip()

    # 图片去重
    images = []

    for image_url in parser.images:
        if not image_url:
            continue

        if image_url.startswith("//"):
            image_url = "https:" + image_url

        if image_url not in images:
            images.append(image_url)

    return {
        "text": text,
        "images": images,
    }


# ============================================================
# Medium RSS
# ============================================================

def get_xml_text(node, tag_name):
    child = node.find(tag_name)

    if child is None:
        return ""

    return child.text or ""


def get_atom_link(entry):
    namespace = "{http://www.w3.org/2005/Atom}"

    for link_node in entry.findall(namespace + "link"):
        href = link_node.attrib.get("href", "")

        if href:
            return href

    return ""


def fetch_medium_feed(source_name, feed_url):
    print()
    print("=" * 70)
    print(f"抓取 Medium：{source_name}")
    print(feed_url)
    print("=" * 70)

    try:
        xml_data = http_get(feed_url)
        root = ET.fromstring(xml_data)
    except Exception as e:
        print(f"Medium RSS 抓取失败：{e}")
        return []

    namespace = {
        "atom": "http://www.w3.org/2005/Atom",
        "content": "http://purl.org/rss/1.0/modules/content/",
        "dc": "http://purl.org/dc/elements/1.1/",
    }

    articles = []

    # Medium 通常使用 Atom <entry>
    entries = root.findall("atom:entry", namespace)

    # 兼容普通 RSS
    if not entries:
        entries = root.findall(".//item")

    for entry in entries[:MAX_ITEMS_PER_SOURCE]:

        title = ""
        link = ""
        pub_date = ""
        summary = ""
        content_html = ""

        # Atom
        title_node = entry.find("atom:title", namespace)

        if title_node is not None:
            title = title_node.text or ""

        link = get_atom_link(entry)

        published_node = entry.find(
            "atom:published",
            namespace
        )

        updated_node = entry.find(
            "atom:updated",
            namespace
        )

        if published_node is not None:
            pub_date = published_node.text or ""
        elif updated_node is not None:
            pub_date = updated_node.text or ""

        summary_node = entry.find(
            "atom:summary",
            namespace
        )

        if summary_node is not None:
            summary = summary_node.text or ""

        content_node = entry.find(
            "atom:content",
            namespace
        )

        if content_node is not None:
            content_html = "".join(
                content_node.itertext()
            )

            # 如果 content 节点本身带 XHTML 内容，
            # itertext 只能得到文字，因此重新取原始序列化内容
            try:
                content_html = ET.tostring(
                    content_node,
                    encoding="unicode"
                )
            except Exception:
                pass

        # 普通 RSS 兼容
        if not title:
            title = get_xml_text(entry, "title")

        if not link:
            link = get_xml_text(entry, "link")

        if not pub_date:
            pub_date = get_xml_text(
                entry,
                "pubDate"
            )

        if not summary:
            summary = get_xml_text(
                entry,
                "description"
            )

        if not content_html:
            content_html = get_xml_text(
                entry,
                "{http://purl.org/rss/1.0/modules/content/}encoded"
            )

        title = clean_text(title)
        link = normalize_url(link)
        summary_text = strip_html(summary)

        # Medium RSS 的 content 如果是 HTML，
        # 直接解析 HTML。
        parsed = parse_html_content(
            content_html
        )

        body_text = parsed["text"]
        images = parsed["images"]

        # 如果正文解析失败，至少保留 summary
        if len(body_text) < 300:
            body_text = summary_text

        # Medium 付费墙文章通常不会提供完整 RSS 正文。
        # 正文过短直接跳过，不尝试绕过付费墙。
        if len(body_text) < 500:
            print(
                f"跳过 Medium 文章：正文过短 / 可能是付费墙"
            )
            print(f"标题：{title}")
            continue

        if not title or not link:
            continue

        articles.append({
            "source": "Medium",
            "source_name": source_name,
            "title": title,
            "summary": summary_text,
            "link": link,
            "pub_date": pub_date,
            "body": truncate_text(
                body_text,
                MAX_ARTICLE_CHARS
            ),
            "images": images[:10],
        })

    print(
        f"Medium {source_name} 获取到 {len(articles)} 篇可用文章"
    )

    return articles


# ============================================================
# DEV.to
# ============================================================

def fetch_dev_articles():
    print()
    print("=" * 70)
    print("抓取 DEV.to")
    print("=" * 70)

    articles = []
    seen_ids = set()

    for tag in DEV_TAGS:

        url = (
            f"{DEV_API_BASE}/articles"
            f"?tag={urllib.parse.quote(tag)}"
            f"&per_page={MAX_ITEMS_PER_SOURCE}"
        )

        print()
        print(f"DEV.to 标签：{tag}")

        try:
            data = http_json_get(
                url,
                headers={
                    "Accept": "application/json"
                }
            )
        except Exception as e:
            print(
                f"DEV.to 标签 {tag} 获取失败：{e}"
            )
            continue

        if not isinstance(data, list):
            continue

        for item in data:

            article_id = item.get("id")

            if not article_id:
                continue

            if article_id in seen_ids:
                continue

            seen_ids.add(article_id)

            title = clean_text(
                item.get("title", "")
            )

            description = clean_text(
                item.get("description", "")
            )

            url_value = (
                item.get("url")
                or ""
            )

            published_at = (
                item.get("published_at")
                or item.get("published_timestamp")
                or ""
            )

            cover_image = (
                item.get("cover_image")
                or item.get("social_image")
                or ""
            )

            tags = item.get("tag_list", [])

            if isinstance(tags, str):
                tags = [
                    x.strip()
                    for x in tags.split(",")
                    if x.strip()
                ]

            if not title or not url_value:
                continue

            articles.append({
                "source": "DEV.to",
                "source_name": "DEV.to",
                "id": article_id,
                "title": title,
                "summary": description,
                "link": normalize_url(url_value),
                "pub_date": published_at,
                "cover_image": normalize_url(
                    cover_image
                ),
                "tags": tags,
            })

    print(
        f"DEV.to 初步获取 {len(articles)} 篇文章"
    )

    # --------------------------------------------------------
    # 获取每篇文章的完整正文
    # --------------------------------------------------------

    completed = []

    # 最多处理前 30 篇，避免一次运行请求太多
    for index, article in enumerate(
        articles[:30],
        start=1
    ):

        article_id = article.get("id")

        print(
            f"\n读取 DEV.to 正文 "
            f"{index}/{min(len(articles), 30)}："
            f"{article['title']}"
        )

        detail_url = (
            f"{DEV_API_BASE}/articles/{article_id}"
        )

        try:
            detail = http_json_get(
                detail_url,
                headers={
                    "Accept": "application/json"
                }
            )
        except Exception as e:
            print(
                f"DEV.to 正文获取失败：{e}"
            )
            continue

        body_html = (
            detail.get("body_html")
            or ""
        )

        body_markdown = (
            detail.get("body_markdown")
            or ""
        )

        if body_html:
            parsed = parse_html_content(
                body_html
            )

            body_text = parsed["text"]
            images = parsed["images"]

        else:
            body_text = clean_text(
                body_markdown
            )
            images = []

        if not body_text:
            continue

        if len(body_text) < 500:
            print("正文过短，跳过")
            continue

        if not images:
            cover_image = (
                detail.get("cover_image")
                or detail.get("social_image")
                or article.get("cover_image")
                or ""
            )

            if cover_image:
                images = [
                    normalize_url(cover_image)
                ]

        completed.append({
            "source": "DEV.to",
            "source_name": "DEV.to",
            "title": clean_text(
                detail.get(
                    "title",
                    article["title"]
                )
            ),
            "summary": clean_text(
                detail.get(
                    "description",
                    article["summary"]
                )
            ),
            "link": normalize_url(
                detail.get(
                    "url",
                    article["link"]
                )
            ),
            "pub_date": (
                detail.get("published_at")
                or article["pub_date"]
            ),
            "body": truncate_text(
                body_text,
                MAX_ARTICLE_CHARS
            ),
            "images": images[:10],
            "tags": detail.get(
                "tag_list",
                article.get("tags", [])
            ),
        })

    print(
        f"DEV.to 获取到 {len(completed)} 篇完整文章"
    )

    return completed


# ============================================================
# 文章关键词过滤
# ============================================================

POSITIVE_KEYWORDS = [
    "frontend",
    "front-end",
    "web",
    "javascript",
    "typescript",
    "react",
    "vue",
    "angular",
    "css",
    "html",
    "browser",
    "web development",
    "ui",
    "ux",
    "next.js",
    "nuxt",
    "vite",
    "webpack",
    "performance",
    "accessibility",
    "ai",
    "artificial intelligence",
    "llm",
    "large language model",
    "generative ai",
    "copilot",
    "agent",
    "ai coding",
    "coding agent",
]

NEGATIVE_KEYWORDS = [
    "job",
    "jobs",
    "hiring",
    "recruit",
    "recruitment",
    "giveaway",
    "sponsor",
    "sponsored",
    "newsletter",
    "roundup",
    "weekly roundup",
    "monthly roundup",
    "introducing myself",
    "looking for work",
    "crypto",
    "cryptocurrency",
    "bitcoin",
    "casino",
    "betting",
]


def article_keyword_filter(article):
    text = " ".join([
        article.get("title", ""),
        article.get("summary", ""),
        " ".join(
            article.get("tags", [])
            if isinstance(
                article.get("tags", []),
                list
            )
            else []
        ),
    ]).lower()

    positive_score = 0

    for keyword in POSITIVE_KEYWORDS:
        if keyword in text:
            positive_score += 1

    negative_score = 0

    for keyword in NEGATIVE_KEYWORDS:
        if keyword in text:
            negative_score += 1

    if negative_score > 0:
        return False

    if positive_score <= 0:
        return False

    return True


def filter_articles(articles):
    result = []
    seen_links = set()

    for article in articles:

        link = article.get("link", "")

        if not link:
            continue

        if link in seen_links:
            continue

        seen_links.add(link)

        if not article_keyword_filter(article):
            continue

        body = article.get("body", "")

        if len(body) < 500:
            continue

        result.append(article)

    # 优先较新的文章
    result.sort(
        key=lambda x: x.get(
            "pub_date",
            ""
        ),
        reverse=True
    )

    return result


# ============================================================
# SiliconFlow
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
        "enable_thinking": False,
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

        # 每一次重试重新创建 Request
        request = urllib.request.Request(
            SILICONFLOW_URL,
            data=data,
            headers={
                "Content-Type": "application/json",
                "Authorization": (
                    f"Bearer {SILICONFLOW_API_KEY}"
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

            result = json.loads(
                response_data.decode(
                    "utf-8",
                    errors="replace"
                )
            )

            content = (
                result
                .get("choices", [{}])[0]
                .get("message", {})
                .get("content", "")
            )

            if not content:
                raise RuntimeError(
                    "SiliconFlow 返回内容为空"
                )

            print("SiliconFlow 调用成功")

            return content

        except (
            urllib.error.HTTPError,
            urllib.error.URLError,
            TimeoutError,
            socket_timeout_error
        ) as e:

            last_error = e

            print(
                f"SiliconFlow 请求失败：{e}"
            )

        except Exception as e:

            last_error = e

            print(
                f"SiliconFlow 调用失败：{e}"
            )

        if attempt < MAX_RETRIES:

            print(
                f"{RETRY_WAIT_SECONDS} 秒后自动重试..."
            )

            time.sleep(
                RETRY_WAIT_SECONDS
            )

    raise RuntimeError(
        f"SiliconFlow 连续 {MAX_RETRIES} 次调用失败："
        f"{last_error}"
    )


# ============================================================
# socket timeout 类型兼容
# ============================================================

import socket

socket_timeout_error = socket.timeout


# ============================================================
# JSON 提取
# ============================================================

def extract_json(text):

    if not text:
        raise RuntimeError(
            "AI 返回为空，无法解析 JSON"
        )

    text = text.strip()

    # 去掉 markdown code fence
    text = re.sub(
        r"^```json\s*",
        "",
        text,
        flags=re.IGNORECASE
    )

    text = re.sub(
        r"^```\s*",
        "",
        text
    )

    text = re.sub(
        r"\s*```$",
        "",
        text
    )

    text = text.strip()

    try:
        return json.loads(text)
    except Exception:
        pass

    # 尝试截取第一个 JSON 对象
    start = text.find("{")
    end = text.rfind("}")

    if start >= 0 and end > start:

        candidate = text[
            start:end + 1
        ]

        try:
            return json.loads(
                candidate
            )
        except Exception:
            pass

    raise RuntimeError(
        "无法从 AI 返回内容中解析 JSON：\n"
        + text[:3000]
    )


# ============================================================
# AI 选题
# ============================================================

def build_screening_context(articles):

    blocks = []

    for index, article in enumerate(
        articles,
        start=1
    ):

        tags = article.get(
            "tags",
            []
        )

        if not isinstance(tags, list):
            tags = []

        block = f"""
【候选文章 {index}】
来源：{article.get("source", "")}
标题：{article.get("title", "")}
发布时间：{article.get("pub_date", "")}
标签：{", ".join(tags)}
链接：{article.get("link", "")}
简介：{article.get("summary", "")}

原文正文：
{truncate_text(article.get("body", ""), 3000)}
"""

        blocks.append(block)

    context = "\n".join(blocks)

    return truncate_text(
        context,
        MAX_SCREENING_CONTEXT_CHARS
    )


def select_article(articles):

    if not articles:
        raise RuntimeError(
            "没有可供 AI 筛选的文章"
        )

    context = build_screening_context(
        articles
    )

    prompt = f"""
你是一个中文技术公众号编辑。

公众号名称：web前端开发之旅

今天的选题范围：

1. Web 前端技术
2. 前端工程化
3. JavaScript / TypeScript
4. React / Vue / Angular
5. CSS / HTML / 浏览器
6. Web 性能
7. 前端 AI
8. AI Coding
9. LLM 与 Web 开发结合
10. AI Agent 与前端开发结合

下面是今天抓取到的候选原文。

你的任务不是写文章，而是从中选择一篇最适合今天公众号深入改写的文章。

选择标准：

- 必须与 Web 前端或 Web + AI 有直接关系
- 必须有足够完整的技术内容
- 更偏技术实践、原理、工程经验，而不是新闻搬运
- 排除招聘、推广、抽奖、newsletter、roundup
- 排除明显标题党
- 排除正文过短的文章
- 不要因为英文标题看起来热门就选择
- 必须根据实际提供的正文判断

非常重要：

只能根据下面提供的内容判断。
不要补充候选文章中没有出现的信息。

只返回 JSON：

{{
  "selected_index": 1,
  "reason": "简短说明为什么选择这篇"
}}

候选文章：

{context}
"""

    result = call_ai(
        prompt,
        max_tokens=1200
    )

    data = extract_json(result)

    selected_index = data.get(
        "selected_index"
    )

    try:
        selected_index = int(
            selected_index
        )
    except Exception:
        raise RuntimeError(
            "AI 返回的 selected_index 不是数字"
        )

    if not (
        1 <= selected_index <= len(articles)
    ):
        raise RuntimeError(
            f"AI 选择序号无效：{selected_index}"
        )

    selected = articles[
        selected_index - 1
    ]

    print()
    print("=" * 70)
    print("AI 最终选题")
    print("=" * 70)
    print(
        f"标题：{selected['title']}"
    )
    print(
        f"来源：{selected['source']}"
    )
    print(
        f"链接：{selected['link']}"
    )
    print(
        f"选择理由：{data.get('reason', '')}"
    )
    print("=" * 70)

    return selected


# ============================================================
# AI 生成公众号文章
# ============================================================

def generate_article(source_article):

    title = source_article.get(
        "title",
        ""
    )

    source = source_article.get(
        "source",
        ""
    )

    original_link = source_article.get(
        "link",
        ""
    )

    pub_date = source_article.get(
        "pub_date",
        ""
    )

    body = source_article.get(
        "body",
        ""
    )

    prompt = f"""
你是一名中文 Web 前端技术公众号编辑。

公众号：
web前端开发之旅

现在需要把一篇英文 Web 技术文章，改写成一篇中文微信公众号技术文章。

【原文信息】

来源：
{source}

原文标题：
{title}

发布时间：
{pub_date}

原文链接：
{original_link}

【原文正文】

{truncate_text(body, MAX_ARTICLE_CHARS)}

============================================================
写作要求
============================================================

第一原则：

必须严格基于原文。

禁止编造：

- 人物
- 公司
- 产品
- 技术特性
- API
- 性能数据
- Benchmark
- 百分比
- 用户规模
- 时间
- 项目背景
- 原文没有出现的技术结论
- 原文没有出现的因果关系

如果原文没有提供某项信息，就不要自行补充。

不要写：

“据业内人士认为”
“业内普遍认为”
“这意味着……”
“未来一定……”
“有望……”
“必将……”
“相信……”
“可以看出……”
等没有原文事实依据的判断。

可以做正常的中文技术解释，但解释必须能够从原文内容直接推导出来。

============================================================
文章定位
============================================================

不是翻译。

而是：

“准确理解原文后，用中文重新组织成一篇适合中国开发者阅读的技术文章。”

可以：

- 调整段落顺序
- 合并重复内容
- 把英文表达转换成自然中文
- 重新设计小标题
- 对代码示例重新命名变量
- 使用不同的示例数据
- 使用不同的代码场景表达同一个技术点

但不能改变原文技术含义。

============================================================
文章结构
============================================================

必须输出：

1. title
2. lead
3. sections
4. ending

sections 最多 4 个。

每个 section：

{{
  "heading": "小标题",
  "paragraphs": [
    "第一段",
    "第二段"
  ]
}}

如果需要，可以增加：

{{
  "type": "subsection",
  "heading": "小标题",
  "paragraphs": [...]
}}

或者：

{{
  "type": "highlight",
  "text": "重点说明"
}}

或者：

{{
  "type": "list",
  "items": [
    "项目一",
    "项目二"
  ]
}}

============================================================
公众号风格
============================================================

开头不要写成新闻播报。

第一段要直接告诉读者：

“这篇文章到底解决了什么问题？”

然后逐步解释：

问题 → 原理 → 实现 → 注意事项 → 总结

文章应该像一个有经验的前端开发者在给其他开发者讲技术。

语言：

- 中文自然
- 简洁
- 清楚
- 有技术含量
- 不要翻译腔
- 不要过度营销
- 不要 AI 味
- 不要为了凑字数重复观点

关键技术名词可以使用英文。

代码不要大量复制原文。

如果原文存在代码，可以保留必要的代码思路，并允许修改变量名、数据和示例场景。

============================================================
标题
============================================================

标题要适合微信公众号。

不要：

- 标题党
- 夸张
- 虚构结果
- 虚构性能提升
- 虚构“重大突破”

标题应该准确反映原文核心技术主题。

============================================================
输出格式
============================================================

只返回合法 JSON。

不要 Markdown。

格式：

{{
  "title": "文章标题",
  "lead": "开头导语",
  "sections": [
    {{
      "heading": "第一部分",
      "paragraphs": [
        "正文"
      ]
    }}
  ],
  "ending": "结尾总结"
}}

不要输出 source 和 original_link。

程序会自动补充来源信息。

"""

    result = call_ai(
        prompt,
        max_tokens=5000
    )

    data = extract_json(result)

    if not isinstance(data, dict):
        raise RuntimeError(
            "AI 文章结果不是 JSON 对象"
        )

    title = clean_text(
        data.get("title", "")
    )

    lead = clean_text(
        data.get("lead", "")
    )

    ending = clean_text(
        data.get("ending", "")
    )

    sections = data.get(
        "sections",
        []
    )

    if not title:
        raise RuntimeError(
            "AI 没有生成文章标题"
        )

    if not lead:
        raise RuntimeError(
            "AI 没有生成文章导语"
        )

    if not ending:
        raise RuntimeError(
            "AI 没有生成文章结尾"
        )

    if not isinstance(
        sections,
        list
    ):
        raise RuntimeError(
            "AI 返回的 sections 格式错误"
        )

    # 最多保留 4 个章节
    sections = sections[:4]

    normalized_sections = []

    for section in sections:

        if not isinstance(
            section,
            dict
        ):
            continue

        heading = clean_text(
            section.get(
                "heading",
                ""
            )
        )

        paragraphs = section.get(
            "paragraphs",
            []
        )

        if not isinstance(
            paragraphs,
            list
        ):
            paragraphs = []

        clean_paragraphs = []

        for paragraph in paragraphs:

            if not isinstance(
                paragraph,
                str
            ):
                continue

            paragraph = paragraph.strip()

            if paragraph:
                clean_paragraphs.append(
                    paragraph[:MAX_SECTION_CHARS]
                )

        if heading and clean_paragraphs:

            normalized_sections.append({
                "heading": heading,
                "paragraphs": clean_paragraphs
            })

    if not normalized_sections:
        raise RuntimeError(
            "AI 没有生成有效正文 sections"
        )

    article = {
        "title": title,
        "lead": lead,
        "sections": normalized_sections,
        "ending": ending,
        "content_type": "web_frontend_tech",
        "content_type_name": "Web前端技术",
        "source": source_article.get(
            "source",
            ""
        ),
        "original_link": source_article.get(
            "link",
            ""
        ),
        "pub_date": source_article.get(
            "pub_date",
            ""
        ),
        "news_title": source_article.get(
            "title",
            ""
        ),
    }

    return article


# ============================================================
# 下载封面
# ============================================================

def is_valid_image_content(data):
    if not data:
        return False

    # JPEG
    if data.startswith(b"\xff\xd8\xff"):
        return True

    # PNG
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return True

    # WEBP
    if data.startswith(b"RIFF") and b"WEBP" in data[:16]:
        return True

    return False


def download_cover(image_urls):

    if not image_urls:
        print(
            "原文没有找到图片，无法下载 cover.jpg"
        )
        return False

    for index, image_url in enumerate(
        image_urls,
        start=1
    ):

        if not image_url:
            continue

        print()
        print(
            f"尝试下载封面图片 "
            f"{index}/{len(image_urls)}"
        )
        print(image_url)

        try:
            data = http_get(
                image_url,
                headers={
                    "Accept": (
                        "image/avif,image/webp,"
                        "image/apng,image/svg+xml,"
                        "image/*,*/*;q=0.8"
                    ),
                    "Referer": (
                        "https://medium.com/"
                        if "medium.com" in image_url
                        else "https://dev.to/"
                    )
                },
                timeout=30
            )

            if not is_valid_image_content(
                data
            ):
                print(
                    "下载内容不是常见图片格式，跳过"
                )
                continue

            # 微信素材接口对图片大小有限制，
            # 这里控制在较合理范围。
            if len(data) > 8 * 1024 * 1024:
                print(
                    "图片超过 8MB，跳过"
                )
                continue

            with open(
                COVER_FILE,
                "wb"
            ) as f:
                f.write(data)

            print(
                f"封面图片下载成功："
                f"{COVER_FILE}"
            )

            return True

        except Exception as e:
            print(
                f"图片下载失败：{e}"
            )

    print(
        "所有候选图片均下载失败"
    )

    return False


# ============================================================
# 保存 article.json
# ============================================================

def save_article(article):

    with open(
        ARTICLE_FILE,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            article,
            f,
            ensure_ascii=False,
            indent=2
        )

    print()
    print("=" * 70)
    print(
        f"文章已保存：{ARTICLE_FILE}"
    )
    print(
        f"标题：{article['title']}"
    )
    print(
        f"来源：{article['source']}"
    )
    print(
        f"原文：{article['original_link']}"
    )
    print("=" * 70)


# ============================================================
# 主流程
# ============================================================

def main():

    print()
    print("=" * 70)
    print("Web 前端 + AI 公众号自动化")
    print("Medium + DEV.to → SiliconFlow → article.json")
    print("=" * 70)

    # --------------------------------------------------------
    # 1. 检查 SiliconFlow Key
    # --------------------------------------------------------

    if not SILICONFLOW_API_KEY:
        raise RuntimeError(
            "没有找到 SILICONFLOW_API_KEY"
        )

    # --------------------------------------------------------
    # 2. 抓 Medium
    # --------------------------------------------------------

    all_articles = []

    for source_name, feed_url in MEDIUM_FEEDS:

        medium_articles = fetch_medium_feed(
            source_name,
            feed_url
        )

        all_articles.extend(
            medium_articles
        )

    # --------------------------------------------------------
    # 3. 抓 DEV.to
    # --------------------------------------------------------

    dev_articles = fetch_dev_articles()

    all_articles.extend(
        dev_articles
    )

    print()
    print("=" * 70)
    print(
        f"原始文章总数：{len(all_articles)}"
    )
    print("=" * 70)

    # --------------------------------------------------------
    # 4. 关键词预筛
    # --------------------------------------------------------

    filtered_articles = filter_articles(
        all_articles
    )

    print()
    print("=" * 70)
    print(
        f"关键词过滤后：{len(filtered_articles)} 篇"
    )
    print("=" * 70)

    if not filtered_articles:
        raise RuntimeError(
            "没有找到符合 Web 前端 / AI 条件的文章"
        )

    # --------------------------------------------------------
    # 5. 限制候选数量
    # --------------------------------------------------------

    candidates = filtered_articles[
        :MAX_CANDIDATES_FOR_AI
    ]

    print()
    print("进入 AI 筛选的候选文章：")

    for index, article in enumerate(
        candidates,
        start=1
    ):

        print(
            f"{index}. "
            f"[{article['source']}] "
            f"{article['title']}"
        )

    # --------------------------------------------------------
    # 6. AI 选择最终文章
    # --------------------------------------------------------

    selected_article = select_article(
        candidates
    )

    # --------------------------------------------------------
    # 7. AI 改写公众号文章
    # --------------------------------------------------------

    print()
    print("=" * 70)
    print("开始生成中文公众号文章")
    print("=" * 70)

    article = generate_article(
        selected_article
    )

    # --------------------------------------------------------
    # 8. 保存 article.json
    # --------------------------------------------------------

    save_article(
        article
    )

    # --------------------------------------------------------
    # 9. 下载原文图片作为 cover
    # --------------------------------------------------------

    image_urls = selected_article.get(
        "images",
        []
    )

    # DEV.to 如果正文没有图片，则使用 cover_image
    if not image_urls:

        cover_image = (
            selected_article.get(
                "cover_image",
                ""
            )
        )

        if cover_image:
            image_urls = [
                cover_image
            ]

    download_cover(
        image_urls
    )

    # --------------------------------------------------------
    # 10. 最终检查
    # --------------------------------------------------------

    print()
    print("=" * 70)
    print("news_fetcher.py 执行完成")
    print("=" * 70)

    print(
        f"article.json："
        f"{'存在' if os.path.exists(ARTICLE_FILE) else '不存在'}"
    )

    print(
        f"cover.jpg："
        f"{'存在' if os.path.exists(COVER_FILE) else '不存在'}"
    )

    print()
    print(
        "下一步将由 ai-news.yml 调用 wechat_test.py"
    )
    print(
        "把文章提交到微信公众号草稿箱。"
    )

    print("=" * 70)


if __name__ == "__main__":
    main()
