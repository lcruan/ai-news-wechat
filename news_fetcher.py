import os
import json
import re
import html
import time
import socket
import urllib.request
import urllib.error
import urllib.parse
import xml.etree.ElementTree as ET


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
PROCESSED_NEWS_FILE = "processed_news.json"


# ============================================================
# 新闻源
# ============================================================

# 当前阶段只使用 DEV.to。
# 公众号定位以 Web 前端技术为主，重点关注 Vue、TypeScript、
# JavaScript、React、CSS、Vite、Web 性能等。
DEV_API_URL = "https://dev.to/api/articles"

DEV_TAGS = [
    "frontend",
    "webdev",
    "javascript",
    "typescript",
    "vue",
    "react",
    "css",
    "vite",
]

MAX_NEWS_PER_SOURCE = 20

MAX_SCREENING_SUMMARY_CHARS = 800
MAX_FACT_SUMMARY_CHARS = 2000
MAX_SOURCE_ARTICLE_CHARS = 14000
MAX_SCREENING_CONTEXT_CHARS = 30000


# ============================================================
# 关键词
# ============================================================

FRONTEND_KEYWORDS = [
    "frontend",
    "front-end",
    "web development",
    "web developer",
    "javascript",
    "typescript",
    "react",
    "vue",
    "angular",
    "next.js",
    "nextjs",
    "nuxt",
    "css",
    "html",
    "browser",
    "web performance",
    "webperf",
    "webpack",
    "vite",
    "node.js",
    "nodejs",
    "frontend engineering",
    "web engineering",
]


AI_KEYWORDS = [
    "artificial intelligence",
    "generative ai",
    "genai",
    "ai",
    "llm",
    "large language model",
    "machine learning",
    "deep learning",
    "openai",
    "chatgpt",
    "claude",
    "gemini",
    "copilot",
    "cursor",
    "ai coding",
    "ai programming",
    "coding agent",
    "ai agent",
    "agentic",
]


ROUNDUP_KEYWORDS = [
    "newsletter",
    "weekly roundup",
    "monthly roundup",
    "top ",
    "best ",
    "roundup",
    "digest",
]


# ============================================================
# 通用工具
# ============================================================

def fetch_url(url, timeout=REQUEST_TIMEOUT):
    """
    通用 HTTP GET 请求。
    """

    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 "
                "(X11; Linux x86_64) "
                "AppleWebKit/537.36 "
                "(KHTML, like Gecko) "
                "Chrome/120 Safari/537.36"
            ),
            "Accept": (
                "application/json,"
                "application/xml,"
                "text/xml,"
                "text/html,"
                "*/*"
            ),
        },
        method="GET",
    )

    try:

        with urllib.request.urlopen(
            request,
            timeout=timeout,
        ) as response:

            data = response.read()

            content_type = (
                response.headers.get(
                    "Content-Type",
                    "",
                )
            )

            return data, content_type

    except urllib.error.HTTPError as e:

        error_body = ""

        try:
            error_body = e.read().decode(
                "utf-8",
                errors="ignore",
            )
        except Exception:
            pass

        print(
            f"HTTP 请求失败：{e.code} "
            f"{e.reason}"
        )

        if error_body:
            print(
                error_body[:1000]
            )

        raise

    except (
        urllib.error.URLError,
        TimeoutError,
        socket.timeout,
    ) as e:

        print(
            f"HTTP 请求失败：{str(e)}"
        )

        raise


def clean_text(text):
    """
    清理 HTML、空白字符以及常见实体。
    """

    if text is None:
        return ""

    text = str(text)

    text = html.unescape(text)

    text = re.sub(
        r"<[^>]+>",
        " ",
        text,
    )

    text = re.sub(
        r"\s+",
        " ",
        text,
    )

    return text.strip()


def truncate_text(text, max_chars):
    """
    截断文本，避免发送给 AI 的上下文过长。
    """

    if not text:
        return ""

    text = str(text)

    if len(text) <= max_chars:
        return text

    return text[:max_chars] + "..."


def normalize_url(url):
    """
    规范化 URL。
    """

    if not url:
        return ""

    url = html.unescape(
        str(url).strip()
    )

    if url.startswith("//"):
        url = "https:" + url

    return url


def contains_keyword(text, keywords):
    """
    判断文本是否包含关键词。
    """

    if not text:
        return False

    text = str(text).lower()

    return any(
        keyword.lower() in text
        for keyword in keywords
    )


# ============================================================
# DEV.to
# ============================================================

def fetch_dev_articles(tag):
    print("")
    print("=" * 60)
    print(f"抓取 DEV.to 标签：{tag}")
    print("=" * 60)

    params = urllib.parse.urlencode({
        "tag": tag,
        "per_page": MAX_NEWS_PER_SOURCE,
        "page": 1,
    })

    url = DEV_API_URL + "?" + params

    data, _ = fetch_url(url)

    articles = json.loads(
        data.decode("utf-8")
    )

    results = []

    for item in articles[:MAX_NEWS_PER_SOURCE]:

        article_id = item.get("id")

        title = clean_text(
            item.get("title", "")
        )

        description = clean_text(
            item.get("description", "")
        )

        link = normalize_url(
            item.get("url", "")
        )

        published_at = item.get(
            "published_at",
            "",
        )

        cover_image = (
            item.get("cover_image")
            or item.get("social_image")
            or ""
        )

        if not article_id or not title or not link:
            continue

        full_text = (
            title
            + " "
            + description
        ).lower()

        if not contains_keyword(
            full_text,
            FRONTEND_KEYWORDS,
        ):
            continue

        results.append({
            "source": "DEV.to",
            "id": article_id,
            "title": title,
            "summary": truncate_text(
                description,
                MAX_FACT_SUMMARY_CHARS,
            ),
            "link": link,
            "pubDate": published_at,
            "cover_image": normalize_url(
                cover_image
            ),
            "social_image": normalize_url(
                item.get("social_image", "")
            ),
        })

    print(
        f"DEV.to {tag} 有效文章："
        f"{len(results)}"
    )

    return results


# ============================================================
# 获取 DEV.to 单篇文章完整正文
# ============================================================

def fetch_dev_article_detail(article_id):

    if not article_id:
        raise RuntimeError(
            "DEV.to 文章缺少 id，无法获取完整正文"
        )

    url = f"{DEV_API_URL}/{article_id}"

    print("")
    print("=" * 60)
    print("获取 DEV.to 入选文章完整正文")
    print(f"文章 ID：{article_id}")
    print("=" * 60)

    data, _ = fetch_url(url)

    article = json.loads(
        data.decode("utf-8")
    )

    body_markdown = str(
        article.get(
            "body_markdown",
            "",
        )
        or ""
    ).strip()

    body_html = str(
        article.get(
            "body_html",
            "",
        )
        or ""
    ).strip()

    # 在截断正文之前判断，避免代码位于 14000 字符之后时被漏判。
    source_has_code = source_contains_code_block(body_markdown) or source_contains_code_block(body_html)

    # 同样在截断前提取原文代码，保证最终使用的是完整原文示例。
    source_code_blocks = extract_source_code_blocks(body_markdown)

    if not source_code_blocks:
        source_code_blocks = extract_source_code_blocks(body_html)

    source_content = body_markdown

    if not source_content:
        source_content = clean_text(
            body_html
        )

    source_content = source_content.strip()

    if not source_content:
        raise RuntimeError(
            "DEV.to 入选文章没有可用的正文内容"
        )

    cover_image = normalize_url(
        article.get("cover_image", "")
        or article.get("social_image", "")
        or ""
    )

    if not cover_image:
        cover_image = extract_image_from_html(
            body_html
        )

    print(
        f"DEV.to 完整正文长度："
        f"{len(source_content)} 字符"
    )

    return {
        "source_content": truncate_text(
            source_content,
            MAX_SOURCE_ARTICLE_CHARS,
        ),
        "source_has_code": source_has_code,
        "source_code_blocks": source_code_blocks,
        "cover_image": cover_image,
        "social_image": normalize_url(
            article.get(
                "social_image",
                "",
            )
        ),
    }


# ============================================================
# HTML 图片提取
# ============================================================

def extract_image_from_html(content):

    if not content:
        return ""

    patterns = [
        r'<img[^>]+src=["\']([^"\']+)["\']',
        r'<img[^>]+data-src=["\']([^"\']+)["\']',
        r'<source[^>]+srcset=["\']([^"\']+)["\']',
    ]

    for pattern in patterns:

        match = re.search(
            pattern,
            content,
            flags=re.IGNORECASE,
        )

        if match:

            image_url = html.unescape(
                match.group(1)
            ).strip()

            if image_url.startswith("//"):
                image_url = "https:" + image_url

            if (
                image_url.startswith("http://")
                or image_url.startswith("https://")
            ):
                return image_url

    return ""


# ============================================================
# AI 请求
# ============================================================

def call_ai(messages, max_tokens=4000):

    if not SILICONFLOW_API_KEY:
        raise RuntimeError(
            "没有找到 SILICONFLOW_API_KEY 环境变量"
        )

    # --------------------------------------------------------
    # 使用 SiliconFlow 流式输出。
    #
    # 原来的非流式方式会一直执行 response.read()，只有模型
    # 完整生成后才返回。如果长文章生成时间较长，就可能在
    # 120 秒后触发：The read operation timed out。
    #
    # stream=true 后，程序会持续读取 SSE 数据块并逐步拼接
    # content，从而避免长文本一直卡在一次 response.read()。
    # --------------------------------------------------------
    payload = {
        "model": MODEL,
        "messages": messages,
        "temperature": 0.2,
        "max_tokens": max_tokens,
        "enable_thinking": False,
        "stream": True,
    }

    body = json.dumps(
        payload,
        ensure_ascii=False,
    ).encode("utf-8")

    for attempt in range(
        1,
        MAX_RETRIES + 1,
    ):

        print("")

        print(
            f"正在调用 SiliconFlow，第 "
            f"{attempt}/{MAX_RETRIES} 次..."
        )

        request = urllib.request.Request(
            SILICONFLOW_URL,
            data=body,
            headers={
                "Content-Type": "application/json",
                "Accept": "text/event-stream",
                "Authorization": (
                    "Bearer "
                    + SILICONFLOW_API_KEY
                ),
                "User-Agent": "AI-News-Automation/1.0",
            },
            method="POST",
        )

        try:

            content_parts = []
            trace_id = ""

            with urllib.request.urlopen(
                request,
                timeout=REQUEST_TIMEOUT,
            ) as response:

                # SiliconFlow 会在响应头中提供 trace id，出现异常时
                # 打印出来方便后续排查服务端请求。
                trace_id = (
                    response.headers.get("X-Trace-Id")
                    or response.headers.get("x-trace-id")
                    or ""
                )

                if trace_id:
                    print(
                        f"SiliconFlow Trace ID：{trace_id}"
                    )

                while True:

                    line = response.readline()

                    if not line:
                        break

                    line = line.decode(
                        "utf-8",
                        errors="replace",
                    ).strip()

                    if not line:
                        continue

                    # SSE 格式通常为：data: {...}
                    if not line.startswith("data:"):
                        continue

                    data_text = line[5:].strip()

                    if not data_text:
                        continue

                    if data_text == "[DONE]":
                        break

                    try:
                        chunk = json.loads(data_text)
                    except json.JSONDecodeError:
                        # 单个 SSE 数据块异常时不要立即丢弃整个请求。
                        # 后续块仍然可能包含完整内容。
                        print(
                            "SiliconFlow 返回了无法解析的流式数据块，"
                            "已跳过。"
                        )
                        continue

                    # OpenAI 兼容 SSE 格式：
                    # choices[0].delta.content
                    choices = chunk.get("choices", [])

                    if not choices:
                        continue

                    delta = choices[0].get("delta", {}) or {}

                    piece = delta.get("content", "")

                    if piece:
                        content_parts.append(piece)

            content = "".join(content_parts)

            if not content:
                raise RuntimeError(
                    "SiliconFlow 流式返回内容为空"
                    + (
                        f"，Trace ID：{trace_id}"
                        if trace_id
                        else ""
                    )
                )

            print(
                "SiliconFlow 流式调用成功，"
                f"收到 {len(content)} 个字符。"
            )

            return content

        except urllib.error.HTTPError as e:

            error_body = ""

            try:
                error_body = e.read().decode(
                    "utf-8",
                    errors="ignore",
                )
            except Exception:
                pass

            print(
                f"SiliconFlow HTTP 错误："
                f"{e.code}"
            )

            print(
                error_body[:1000]
            )

            if e.code not in [
                429,
                500,
                502,
                503,
                504,
            ]:
                raise

        except (
            urllib.error.URLError,
            TimeoutError,
            socket.timeout,
        ) as e:

            print(
                "SiliconFlow 请求失败：",
                str(e),
            )

        except Exception as e:

            print(
                "SiliconFlow 请求异常：",
                str(e),
            )

        if attempt < MAX_RETRIES:

            print(
                f"{RETRY_WAIT_SECONDS} 秒后自动重试..."
            )

            time.sleep(
                RETRY_WAIT_SECONDS
            )

    raise RuntimeError(
        f"SiliconFlow 连续 "
        f"{MAX_RETRIES} 次请求失败"
    )

# ============================================================
# 去除 AI 返回的 Markdown JSON 包裹
# ============================================================

def extract_json_from_ai(text):

    text = text.strip()

    if text.startswith("```"):

        text = re.sub(
            r"^```(?:json)?\s*",
            "",
            text,
            flags=re.IGNORECASE,
        )

        text = re.sub(
            r"\s*```$",
            "",
            text,
        )

    start = text.find("{")
    end = text.rfind("}")

    if start >= 0 and end > start:
        text = text[
            start:end + 1
        ]

    return text


# ============================================================
# 已处理文章记录
#
# 只有微信公众号草稿成功创建后才会写入。
# 这样如果微信接口失败，下次仍然可以重试同一篇。
# ============================================================

def load_processed_news():

    if not os.path.exists(PROCESSED_NEWS_FILE):
        return set()

    try:
        with open(PROCESSED_NEWS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        if isinstance(data, dict):
            links = data.get("links", [])
        elif isinstance(data, list):
            links = data
        else:
            links = []

        processed_links = {
            normalize_url(link)
            for link in links
            if normalize_url(link)
        }

        # 兼容本次升级前已经生成过的 article.json：
        # 至少把最近一篇已经生成的文章视为已处理，
        # 避免升级后的第一次运行又选回同一篇。
        if os.path.exists(ARTICLE_FILE):
            try:
                with open(ARTICLE_FILE, "r", encoding="utf-8") as f:
                    last_article = json.load(f)

                last_link = normalize_url(
                    last_article.get("original_link", "")
                    if isinstance(last_article, dict)
                    else ""
                )

                if last_link:
                    processed_links.add(last_link)
                    print(
                        "已将 article.json 中最近一篇文章加入已处理记录：",
                        last_link
                    )

            except Exception as e:
                print(
                    "读取 article.json 最近文章失败：",
                    str(e)
                )

        return processed_links

    except Exception as e:
        raise RuntimeError(
            "读取 processed_news.json 失败。为避免重复生成文章，"
            f"本次运行已停止：{e}"
        )


def filter_unprocessed_news(news_list, processed_links):

    result = []

    for item in news_list:
        link = normalize_url(item.get("link", ""))

        if not link:
            continue

        if link in processed_links:
            print("跳过已处理文章：", item.get("title", ""))
            continue

        result.append(item)

    return result


# ============================================================
# AI 筛选
# ============================================================

def ai_select_news(news_list):

    if not news_list:
        raise RuntimeError(
            "没有可供 AI 筛选的新闻"
        )

    compact_news = []

    for index, item in enumerate(
        news_list
    ):

        compact_news.append({
            "id": index,
            "source": item.get(
                "source",
                "",
            ),
            "title": item.get(
                "title",
                "",
            ),
            "summary": truncate_text(
                item.get(
                    "summary",
                    "",
                ),
                MAX_SCREENING_SUMMARY_CHARS,
            ),
            "link": item.get(
                "link",
                "",
            ),
            "pubDate": item.get(
                "pubDate",
                "",
            ),
        })

    context = json.dumps(
        compact_news,
        ensure_ascii=False,
    )

    if len(context) > MAX_SCREENING_CONTEXT_CHARS:

        context = context[
            :MAX_SCREENING_CONTEXT_CHARS
        ]

    prompt = f"""
你是一名技术新闻编辑。

下面是今天从 DEV.to 获取的公开文章。

请从中筛选出一篇最适合“web前端开发之旅”公众号今天发布的文章。

公众号主要关注 Web 前端技术，重点包括：

- Vue / Vue 生态
- TypeScript
- JavaScript
- React / Next.js
- CSS / HTML
- Vite / Webpack / 前端工程化
- 浏览器与 Web 性能
- Node.js 与 Web 开发
- AI + Web、AI 编程等与前端直接相关的内容

要求：

1. 只能根据提供的标题、摘要、来源和链接判断。
2. 不允许根据自己的知识补充新闻事实。
3. 优先选择真正的 Web 前端技术内容。
4. AI 相关内容只有在与 Web 前端开发存在直接关系时才优先考虑。
5. 排除 newsletter、weekly roundup、monthly roundup 等汇总文章。
6. 不选择明显重复的内容。
7. 不要选择明显只是推广、广告或招聘的内容。
8. 优先选择原文信息足够丰富、能够写成一篇完整中文技术文章的内容。
9. 最终只能选择 1 篇。

返回严格 JSON：

{{
  "selected_id": 0,
  "score": 8,
  "reason": "简短说明选择原因",
  "duplicate_group": "用于判断重复内容的简短标识"
}}

新闻：

{context}
"""

    result = call_ai(
        [
            {
                "role": "user",
                "content": prompt,
            }
        ],
        max_tokens=1200,
    )

    result = extract_json_from_ai(
        result
    )

    data = json.loads(
        result
    )

    selected_id = int(
        data.get(
            "selected_id",
            0,
        )
    )

    if (
        selected_id < 0
        or selected_id >= len(news_list)
    ):
        raise RuntimeError(
            f"AI 返回的 selected_id 无效："
            f"{selected_id}"
        )

    selected = news_list[
        selected_id
    ].copy()

    selected["ai_score"] = data.get(
        "score",
        0,
    )

    selected["ai_reason"] = data.get(
        "reason",
        "",
    )

    selected["duplicate_group"] = data.get(
        "duplicate_group",
        "",
    )

    return selected


# ============================================================
# 清理代码块
# ============================================================

def clean_code_block(code):

    if code is None:
        return ""

    code = str(code)

    # 统一换行
    code = code.replace(
        "\r\n",
        "\n",
    ).replace(
        "\r",
        "\n",
    )

    # 去掉代码块两侧多余空行
    code = code.strip()

    # 如果 AI 又返回了 ``` 包裹，
    # 这里去掉外层 Markdown 标记。
    code = re.sub(
        r"^```[a-zA-Z0-9_+#.-]*\s*\n?",
        "",
        code,
    )

    code = re.sub(
        r"\n?```\s*$",
        "",
        code,
    )

    return code.strip()


def clean_code_language(language):

    if not language:
        return "text"

    language = str(
        language
    ).strip().lower()

    language_map = {
        "js": "javascript",
        "jsx": "javascript",
        "ts": "typescript",
        "tsx": "typescript",
        "vue": "vue",
        "html": "html",
        "css": "css",
        "scss": "scss",
        "sass": "sass",
        "json": "json",
        "bash": "bash",
        "shell": "bash",
        "sh": "bash",
        "yml": "yaml",
        "md": "markdown",
        "py": "python",
    }

    return language_map.get(
        language,
        language,
    )


# ============================================================
# 提取原文中的真实代码块
#
# 最终文章中的代码直接来自原文，不让 AI 改写。
# ============================================================

def extract_source_code_blocks(source_content):

    if not source_content:
        return []

    text = str(source_content)
    results = []

    # Markdown fenced code
    fenced_pattern = re.compile(
        r"(?ms)^\s*```([^\n`]*)\n(.*?)^\s*```\s*$"
    )

    for match in fenced_pattern.finditer(text):

        language = clean_code_language(
            match.group(1).strip() or "text"
        )

        code = clean_code_block(
            match.group(2)
        )

        if code:
            results.append({
                "language": language,
                "code": code,
            })

    # HTML <pre> / <pre><code> code
    html_pattern = re.compile(
        r"(?is)<pre\b([^>]*)>(.*?)</pre\s*>"
    )

    for match in html_pattern.finditer(text):

        attrs = match.group(1) or ""
        inner = match.group(2) or ""

        language_match = re.search(
            r"(?:language|lang)-([a-zA-Z0-9_+#.-]+)",
            attrs + " " + inner[:300],
            flags=re.IGNORECASE,
        )

        language = clean_code_language(
            language_match.group(1)
            if language_match
            else "text"
        )

        inner = re.sub(
            r"(?is)^\s*<code\b[^>]*>",
            "",
            inner,
        )

        inner = re.sub(
            r"(?is)</code\s*>\s*$",
            "",
            inner,
        )

        inner = re.sub(
            r"<[^>]+>",
            "",
            inner,
        )

        code = clean_code_block(
            html.unescape(inner)
        )

        if not code:
            continue

        if not any(
            item["code"] == code
            for item in results
        ):
            results.append({
                "language": language,
                "code": code,
            })

    return results


# ============================================================
# 判断原文是否存在真正的代码块
#
# 单反引号 inline code 不算代码块。
# 只识别 Markdown fenced code、HTML pre/code、
# 以及连续的 Markdown 缩进代码块。
# ============================================================

def source_contains_code_block(source_content):

    if not source_content:
        return False

    text = str(source_content)

    if re.search(
        r"(?ms)^\s*```(?:[\w+#.-]+)?\s*$.*?^\s*```\s*$",
        text,
    ):
        return True

    if re.search(
        r"<pre\b[^>]*>.*?</pre\s*>",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    ):
        return True

    if re.search(
        r"<code\b[^>]*>.*?</code\s*>",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    ):
        return True

    consecutive = 0
    for line in text.splitlines():
        if re.match(r"^    \S+", line):
            consecutive += 1
            if consecutive >= 2:
                return True
        elif line.strip():
            consecutive = 0

    return False


def enforce_code_block_source_rule(article, source_has_code):
    """原文没有代码块时，程序强制清空 AI 返回的 code_blocks。"""

    if not isinstance(article, dict):
        return article

    sections = article.get("sections", [])

    if not isinstance(sections, list):
        return article

    if not source_has_code:

        removed = 0

        for section in sections:
            if not isinstance(section, dict):
                continue

            code_blocks = section.get("code_blocks", [])

            if isinstance(code_blocks, list):
                removed += len(code_blocks)

            section["code_blocks"] = []

        if removed:
            print(
                "原文没有代码块，已强制清空 AI 生成的 "
                f"{removed} 个代码块。"
            )
        else:
            print("原文没有代码块，代码示例：0")

    else:
        total = 0
        for section in sections:
            if not isinstance(section, dict):
                continue
            code_blocks = section.get("code_blocks", [])
            if isinstance(code_blocks, list):
                total += len(code_blocks)

        print(
            "检测到原文存在代码块，"
            f"AI 返回代码块：{total} 个。"
        )

    return article


# ============================================================
# 强制使用原文代码
#
# AI 只负责决定代码放在哪个 section。
# code 和 language 最终直接取自原文。
# ============================================================

def enforce_original_code_blocks(
    article,
    source_code_blocks,
    source_has_code,
):

    if not isinstance(article, dict):
        return article

    sections = article.get("sections", [])

    if not isinstance(sections, list):
        return article

    if not source_has_code or not source_code_blocks:

        for section in sections:
            if isinstance(section, dict):
                section["code_blocks"] = []

        return article

    for section in sections:

        if not isinstance(section, dict):
            continue

        code_blocks = section.get("code_blocks", [])

        if not isinstance(code_blocks, list):
            section["code_blocks"] = []
            continue

        exact_blocks = []

        for code_block in code_blocks:

            if not isinstance(code_block, dict):
                continue

            source_index = code_block.get(
                "source_code_index",
                None,
            )

            try:
                source_index = int(source_index)
            except (TypeError, ValueError):
                source_index = None

            selected = None

            if (
                source_index is not None
                and 1 <= source_index <= len(source_code_blocks)
            ):
                selected = source_code_blocks[source_index - 1]

            # 兼容模型没有返回索引、但原样返回了代码的情况。
            if selected is None:
                ai_code = clean_code_block(
                    code_block.get("code", "")
                )

                for source_block in source_code_blocks:
                    if ai_code and ai_code == source_block["code"]:
                        selected = source_block
                        break

            # 只有一个原文代码块时，直接使用它。
            if selected is None and len(source_code_blocks) == 1:
                selected = source_code_blocks[0]

            # 无法确认对应原文代码时，宁可不显示，也不使用 AI 自造代码。
            if selected is None:
                continue

            exact_blocks.append({
                "language": selected.get("language", "text"),
                "caption": clean_text(
                    code_block.get("caption", "")
                ),
                "code": selected.get("code", ""),
            })

        section["code_blocks"] = exact_blocks

    return article


# ============================================================
# AI 生成公众号文章
# ============================================================

def ai_generate_article(news):

    source = news.get(
        "source",
        "",
    )

    title = news.get(
        "title",
        "",
    )

    summary = news.get(
        "summary",
        "",
    )

    source_content = news.get(
        "source_content",
        "",
    )

    link = news.get(
        "link",
        "",
    )

    source_has_code = news.get(
        "source_has_code",
        None,
    )

    if source_has_code is None:
        source_has_code = source_contains_code_block(
            source_content
        )

    pub_date = news.get(
        "pubDate",
        "",
    )

    fact_context = {
        "source": source,
        "title": title,
        "summary": truncate_text(
            summary,
            MAX_SCREENING_SUMMARY_CHARS,
        ),
        "source_content": truncate_text(
            source_content,
            MAX_SOURCE_ARTICLE_CHARS,
        ),
        "original_link": link,
        "pub_date": pub_date,
    }

    prompt = f"""
你是一名中文 Web 前端技术公众号编辑。

请根据下面提供的唯一一篇 DEV.to 英文技术文章原文，
将它忠实地重构成一篇完整的中文微信公众号技术文章。

公众号名称：

web前端开发之旅

这不是简单的新闻摘要。

你需要把原文真正有价值的技术内容提取出来，
让中文 Web 前端开发者能够理解文章讲了什么、
为什么值得关注，以及具体怎么做。

============================================================
一、文章结构
============================================================

文章必须包含：

1. 一个有吸引力但不过度夸张的标题
2. 开场导语
3. 3～4 个正文小节
4. 每个小节包含自然段
5. 如果原文存在重要代码示例，应在相关小节中保留代码
6. 如果原文存在真实案例、项目实践、API 使用场景、配置示例，
   应在相关小节中尽可能保留
7. 最后有一个“写在最后”的总结

============================================================
二、最重要：不要把原文的技术价值删掉
============================================================

这是一篇 Web 前端技术文章。

如果原文中出现以下内容，它们都属于重要信息：

- 实际案例
- 项目实践
- 代码示例
- API 调用示例
- 配置文件
- JavaScript / TypeScript 示例
- Vue / React 示例
- HTML / CSS 示例
- Vite / Webpack 配置
- 浏览器 API 使用方式
- 前后对比代码
- 错误代码与修复代码
- 性能测试或 benchmark
- 实际使用场景

改写时不能为了“简洁”而把这些内容全部删除。

特别是：

只有当 source_content 中确实存在代码块时，才允许生成 code_blocks。

如果原文没有代码块：
- code_blocks 必须严格返回 []
- 不允许为了增强文章可读性而补充示例代码
- 不允许根据自己的知识创造任何代码

如果原文存在多个重要代码示例，
可以选择 1～3 个最核心的代码示例。

代码过长时，可以只保留核心部分，
但必须保证代码仍然忠实于原文的技术含义。

============================================================
三、代码处理规则
============================================================

如果原文存在代码：

1. 只能使用原文中真实存在的代码。
2. 不允许自己重写、改写、补全或创造代码。
3. 不允许修改变量名、API、配置、函数名或代码逻辑。
4. 程序已经提供 source_code_blocks，其中的 code 是原文代码。
5. 需要放代码时，必须通过 source_code_index 指向对应的原文代码。
6. code 字段尽量原样返回；程序最终会直接使用原文 code。
7. 如果某段原文代码与当前小节无关，就不要引用。
8. 每个代码块必须说明语言类型，例如：
   javascript、typescript、vue、html、css、json、bash 等。
9. 代码块必须放到 JSON 的 code_blocks 中。
10. 代码必须尽量放在与它对应的 section 中。

============================================================
四、真实案例处理规则
============================================================

如果原文有真实案例：

必须尽可能保留。

例如原文提到了：

- 某个项目
- 某种实际使用方式
- 某个 API
- 某个组件
- 某个框架
- 某个配置
- 某个实际问题
- 某个解决方案

都可以作为文章正文的重要组成部分。

可以压缩描述，
但不能无理由删除。

但是：

原文没有的案例，绝对不能自己创造。

============================================================
五、事实约束
============================================================

你只能使用下面提供的信息，
尤其是 source_content 中的原文内容。

不要把你自己的 Web 前端知识当成原文事实。

禁止：

- 编造人物
- 编造公司
- 编造项目
- 编造案例
- 编造数字
- 编造性能数据
- 编造 benchmark
- 编造技术细节
- 编造发布时间
- 编造专家观点
- 编造用户反馈
- 编造测试结果
- 编造 API
- 编造代码
- 编造配置
- 编造因果关系

如果资料中没有某个信息，就不要写。

============================================================
六、事实与解释的区别
============================================================

你可以对原文内容进行中文解释，
但是解释必须能够直接由原文支持。

例如：

原文展示了某段 JavaScript 代码，
你可以解释这段代码“做了什么”。

但是不能因为你知道某个 API 的其他能力，
就自行加入原文没有提到的使用方式。

============================================================
七、文章风格
============================================================

- 中文自然
- 清晰
- 技术感
- 有解释性
- 适合 Web 前端开发者阅读
- 不要明显 AI 腔
- 不要写成新闻列表
- 不要堆砌新闻事实
- 不要重复同一个观点
- 段落之间要有自然过渡
- 重点技术概念可以使用加粗 Markdown，例如 **TypeScript**
- 不要使用表格
- 不要使用 emoji

不要使用：

“据报道”
“业内人士认为”
“这意味着”
“有望”
“值得注意的是”

除非这些内容能够直接从提供的事实中得到支持。

============================================================
八、正文长度
============================================================

不要为了追求短而过度压缩。

如果原文是一篇完整技术教程或实践文章，
应保留足够的技术背景、案例和代码，
让最终中文文章本身具有阅读价值。

============================================================
九、严格 JSON 输出
============================================================

必须严格返回 JSON。

不要返回 Markdown 代码块。

格式：

{{
  "title": "文章标题",
  "lead": "开场导语",
  "sections": [
    {{
      "heading": "小节标题",
      "paragraphs": [
        "第一段",
        "第二段"
      ],
      "code_blocks": [
        {{
          "source_code_index": 1,
          "language": "javascript",
          "caption": "这段代码用于做什么",
          "code": "原文中的代码，不要改写"
        }}
      ]
    }}
  ],
  "ending": "写在最后的总结"
}}

注意：

- code_blocks 可以为空数组 []
- 没有代码时不要强行创造代码
- 有代码时尽量保留核心代码
- 最多保留 3 个最有价值的代码块
- 不要把普通文字放进 code_blocks
- 不要把代码放进 paragraphs
- paragraphs 和 code_blocks 必须是数组

来源信息：

{json.dumps(
    fact_context,
    ensure_ascii=False,
    indent=2
)}

其中 source_code_blocks 是从原文直接提取的真实代码。
如果需要代码，必须引用其中已有代码，不能自己生成。

程序预先检测结果：
原文是否存在代码块：{"是" if source_has_code else "否"}

如果检测结果为“否”，必须返回 code_blocks: []。
"""

    result = call_ai(
        [
            {
                "role": "user",
                "content": prompt,
            }
        ],
        max_tokens=6000,
    )

    result = extract_json_from_ai(
        result
    )

    article = json.loads(
        result
    )

    # 程序级硬校验：原文没有代码块时，AI 返回的代码一律丢弃。
    article = enforce_code_block_source_rule(
        article,
        source_has_code,
    )

    # 程序级硬校验：最终代码必须直接来自原文。
    article = enforce_original_code_blocks(
        article,
        news.get("source_code_blocks", []),
        source_has_code,
    )

    title = clean_text(
        article.get(
            "title",
            "",
        )
    )

    lead = clean_text(
        article.get(
            "lead",
            "",
        )
    )

    sections = article.get(
        "sections",
        [],
    )

    ending = clean_text(
        article.get(
            "ending",
            "",
        )
    )

    if not title:
        raise RuntimeError(
            "AI 生成的文章缺少 title"
        )

    if not lead:
        raise RuntimeError(
            "AI 生成的文章缺少 lead"
        )

    if not isinstance(
        sections,
        list,
    ):
        raise RuntimeError(
            "AI 生成的 sections 格式错误"
        )

    cleaned_sections = []

    for section in sections[:4]:

        if not isinstance(
            section,
            dict,
        ):
            continue

        heading = clean_text(
            section.get(
                "heading",
                "",
            )
        )

        paragraphs = section.get(
            "paragraphs",
            [],
        )

        code_blocks = section.get(
            "code_blocks",
            [],
        )

        if not heading:
            continue

        cleaned_paragraphs = []

        if isinstance(
            paragraphs,
            list,
        ):

            for paragraph in paragraphs:

                paragraph = clean_text(
                    str(paragraph)
                )

                if paragraph:
                    cleaned_paragraphs.append(
                        paragraph
                    )

        cleaned_code_blocks = []

        if isinstance(
            code_blocks,
            list,
        ):

            for code_block in code_blocks:

                if not isinstance(
                    code_block,
                    dict,
                ):
                    continue

                language = clean_code_language(
                    code_block.get(
                        "language",
                        "text",
                    )
                )

                try:
                    source_code_index = int(
                        code_block.get(
                            "source_code_index",
                            0,
                        )
                    )
                except (TypeError, ValueError):
                    source_code_index = 0

                caption = clean_text(
                    code_block.get(
                        "caption",
                        "",
                    )
                )

                code = clean_code_block(
                    code_block.get(
                        "code",
                        "",
                    )
                )

                if not code:
                    continue

                cleaned_code_blocks.append({
                    "source_code_index": source_code_index,
                    "language": language,
                    "caption": caption,
                    "code": code,
                })

        if (
            cleaned_paragraphs
            or cleaned_code_blocks
        ):

            cleaned_sections.append({
                "heading": heading,
                "paragraphs": cleaned_paragraphs,
                "code_blocks": cleaned_code_blocks,
            })

    if not cleaned_sections:

        raise RuntimeError(
            "AI 没有生成有效正文"
        )

    return {
        "title": title,
        "lead": lead,
        "sections": cleaned_sections,
        "ending": ending,
        "source": source,
        "original_link": link,
        "pub_date": pub_date,
        "news_title": title,
        "cover_image": news.get(
            "cover_image",
            "",
        ),
    }


# ============================================================
# URL 去重
# ============================================================

def deduplicate_news(news_list):

    result = []
    seen = set()

    for item in news_list:

        link = item.get(
            "link",
            "",
        ).strip()

        if not link:
            continue

        if link in seen:
            continue

        seen.add(link)
        result.append(item)

    return result


# ============================================================
# 新闻过滤
# ============================================================

def filter_news(news_list):

    result = []

    for item in news_list:

        title = item.get(
            "title",
            "",
        ).lower()

        summary = item.get(
            "summary",
            "",
        ).lower()

        text = title + " " + summary

        if any(
            keyword in title
            for keyword in ROUNDUP_KEYWORDS
        ):

            print(
                "跳过汇总类文章：",
                item.get("title"),
            )

            continue

        if not (
            contains_keyword(
                text,
                FRONTEND_KEYWORDS,
            )
            or contains_keyword(
                text,
                AI_KEYWORDS,
            )
        ):
            continue

        result.append(item)

    return result


# ============================================================
# JPEG 判断
# ============================================================

def is_jpeg(data):

    if not data:
        return False

    return data.startswith(
        b"\xff\xd8\xff"
    )


# ============================================================
# 图片 URL 清理
# ============================================================

def normalize_image_url(url):

    if not url:
        return ""

    url = html.unescape(
        url.strip()
    )

    if url.startswith("//"):
        url = "https:" + url

    return url


# ============================================================
# 下载封面
# ============================================================

def download_cover(image_urls):

    print("")
    print("=" * 60)
    print("开始准备公众号封面")
    print("=" * 60)

    existing_cover = None

    if os.path.exists(
        COVER_FILE
    ):

        try:

            with open(
                COVER_FILE,
                "rb",
            ) as f:

                existing_cover = f.read()

            if is_jpeg(
                existing_cover
            ):

                print(
                    "仓库中的 cover.jpg 是有效 JPEG，"
                    "可以作为备用封面"
                )

            else:

                print(
                    "警告：仓库中的 cover.jpg "
                    "不是有效 JPEG，将不会使用"
                )

                existing_cover = None

        except Exception as e:

            print(
                "读取现有 cover.jpg 失败：",
                str(e),
            )

            existing_cover = None

    urls = []

    for url in image_urls:

        url = normalize_image_url(
            url
        )

        if not url:
            continue

        if url not in urls:
            urls.append(url)

    print(
        f"候选封面图片："
        f"{len(urls)} 个"
    )

    for index, image_url in enumerate(
        urls,
        1,
    ):

        print("")
        print(
            f"尝试下载封面 "
            f"{index}/{len(urls)}："
        )

        print(image_url)

        try:

            request_url = image_url

            if (
                "media2.dev.to"
                in request_url
                and "format=auto"
                in request_url
            ):

                request_url = request_url.replace(
                    "format=auto",
                    "format=jpg",
                    1,
                )

                print(
                    "检测到 DEV.to 图片代理的 "
                    "format=auto"
                )

                print(
                    "改为请求 JPEG："
                )

                print(
                    request_url
                )

            request = urllib.request.Request(
                request_url,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 "
                        "(X11; Linux x86_64) "
                        "AppleWebKit/537.36 "
                        "Chrome/120 Safari/537.36"
                    ),
                    "Accept": (
                        "image/avif,image/webp,"
                        "image/apng,image/svg+xml,"
                        "image/*,*/*;q=0.8"
                    ),
                },
                method="GET",
            )

            with urllib.request.urlopen(
                request,
                timeout=30,
            ) as response:

                content_type = (
                    response.headers.get(
                        "Content-Type",
                        "",
                    )
                    .lower()
                    .split(";")[0]
                    .strip()
                )

                data = response.read()

            print(
                f"图片大小："
                f"{len(data)} bytes"
            )

            print(
                f"Content-Type："
                f"{content_type}"
            )

            if not is_jpeg(data):

                print(
                    "跳过：文件内容不是 JPEG"
                )

                continue

            if content_type:

                allowed_types = {
                    "image/jpeg",
                    "image/jpg",
                }

                if content_type not in allowed_types:

                    print(
                        "跳过：Content-Type "
                        f"不是 JPEG，而是 "
                        f"{content_type}"
                    )

                    continue

            with open(
                COVER_FILE,
                "wb",
            ) as f:

                f.write(data)

            with open(
                COVER_FILE,
                "rb",
            ) as f:

                saved_data = f.read()

            if not is_jpeg(
                saved_data
            ):

                print(
                    "错误：保存后的 cover.jpg "
                    "验证失败"
                )

                continue

            print("")
            print(
                "封面下载成功！"
            )

            print(
                f"最终文件："
                f"{COVER_FILE}"
            )

            print(
                f"文件大小："
                f"{len(saved_data)} bytes"
            )

            return True

        except (
            urllib.error.HTTPError,
            urllib.error.URLError,
            TimeoutError,
            socket.timeout,
        ) as e:

            print(
                "图片下载失败：",
                str(e),
            )

        except Exception as e:

            print(
                "处理图片时发生异常：",
                str(e),
            )

    if existing_cover is not None:

        with open(
            COVER_FILE,
            "wb",
        ) as f:

            f.write(
                existing_cover
            )

        print("")
        print(
            "没有找到可用的 JPEG 来源图片。"
        )

        print(
            "已使用仓库中的固定 cover.jpg "
            "作为备用封面。"
        )

        return True

    raise RuntimeError(
        "没有找到可用于微信公众号的 JPEG 封面图片，"
        "并且仓库中也不存在有效的 cover.jpg。"
        "请上传一个真正的 JPEG cover.jpg。"
    )


# ============================================================
# 收集候选封面
# ============================================================

def collect_cover_urls(news):

    urls = []

    cover_image = news.get(
        "cover_image",
        "",
    )

    if cover_image:
        urls.append(
            cover_image
        )

    for key in [
        "social_image",
        "cover_image",
    ]:

        value = news.get(
            key,
            "",
        )

        if value and value not in urls:
            urls.append(value)

    return urls


# ============================================================
# 主流程
# ============================================================

def main():

    print("")
    print("=" * 70)
    print("0元 Web 前端技术公众号自动化")
    print("=" * 70)

    # --------------------------------------------------------
    # 1. 检查 API Key
    # --------------------------------------------------------

    if not SILICONFLOW_API_KEY:

        raise RuntimeError(
            "SILICONFLOW_API_KEY 未配置"
        )

    # --------------------------------------------------------
    # 2. 只抓取 DEV.to
    # --------------------------------------------------------

    all_news = []

    for tag in DEV_TAGS:

        try:

            news = fetch_dev_articles(
                tag
            )

            all_news.extend(
                news
            )

        except Exception as e:

            print("")
            print(
                f"DEV.to {tag} 抓取失败："
            )

            print(
                str(e)
            )

    print("")
    print("=" * 60)

    print(
        f"原始新闻数量："
        f"{len(all_news)}"
    )

    print("=" * 60)

    # --------------------------------------------------------
    # 3. 去重
    # --------------------------------------------------------

    all_news = deduplicate_news(
        all_news
    )

    print(
        f"URL 去重后："
        f"{len(all_news)}"
    )

    # --------------------------------------------------------
    # 4. 关键词过滤
    # --------------------------------------------------------

    all_news = filter_news(
        all_news
    )

    print(
        f"关键词过滤后："
        f"{len(all_news)}"
    )

    if not all_news:

        raise RuntimeError(
            "没有找到符合条件的新闻"
        )

    # --------------------------------------------------------
    # 5. 排除已经成功进入微信公众号草稿箱的文章
    # --------------------------------------------------------

    processed_links = load_processed_news()

    print(
        f"已处理文章数量：{len(processed_links)}"
    )

    unprocessed_news = filter_unprocessed_news(
        all_news,
        processed_links,
    )

    print(
        f"未处理文章数量：{len(unprocessed_news)}"
    )

    if not unprocessed_news:
        raise RuntimeError(
            "当前抓到的文章全部已经处理过，"
            "本次不重复生成公众号文章。"
        )

    # --------------------------------------------------------
    # 6. AI 筛选
    # --------------------------------------------------------

    selected_news = ai_select_news(
        unprocessed_news
    )

    print("")
    print("=" * 60)
    print("AI 最终选择：")
    print("=" * 60)

    print(
        "标题：",
        selected_news.get(
            "title",
            "",
        ),
    )

    print(
        "来源：",
        selected_news.get(
            "source",
            "",
        ),
    )

    print(
        "链接：",
        selected_news.get(
            "link",
            "",
        ),
    )

    print(
        "评分：",
        selected_news.get(
            "ai_score",
            "",
        ),
    )

    # --------------------------------------------------------
    # 7. 获取入选 DEV.to 文章的完整正文
    # --------------------------------------------------------

    detail = fetch_dev_article_detail(
        selected_news.get(
            "id"
        )
    )

    selected_news["source_content"] = detail.get(
        "source_content",
        "",
    )

    selected_news["source_has_code"] = detail.get(
        "source_has_code",
        False,
    )

    selected_news["source_code_blocks"] = detail.get(
        "source_code_blocks",
        [],
    )

    if detail.get(
        "cover_image"
    ):

        selected_news["cover_image"] = detail.get(
            "cover_image"
        )

    if detail.get(
        "social_image"
    ):

        selected_news["social_image"] = detail.get(
            "social_image"
        )

    # --------------------------------------------------------
    # 8. 生成完整公众号文章
    # --------------------------------------------------------

    article = ai_generate_article(
        selected_news
    )

    # --------------------------------------------------------
    # 9. 打印完整公众号文章
    # --------------------------------------------------------

    print("")
    print("=" * 60)
    print("完整公众号文章")
    print("=" * 60)

    print("")
    print(
        f"标题："
        f"{article.get('title', '')}"
    )

    print("")
    print("导语：")
    print(
        article.get(
            "lead",
            "",
        )
    )

    for index, section in enumerate(
        article.get(
            "sections",
            [],
        ),
        1,
    ):

        print("")
        print(
            f"{index:02d}｜"
            f"{section.get('heading', '')}"
        )

        for paragraph in section.get(
            "paragraphs",
            [],
        ):

            print("")
            print(
                paragraph
            )

        code_blocks = section.get(
            "code_blocks",
            [],
        )

        for code_index, code_block in enumerate(
            code_blocks,
            1,
        ):

            print("")

            print(
                f"[代码示例 {code_index}]"
            )

            if code_block.get(
                "caption",
                "",
            ):

                print(
                    "说明：",
                    code_block.get(
                        "caption",
                        "",
                    )
                )

            print(
                "语言：",
                code_block.get(
                    "language",
                    "text",
                )
            )

            print("")

            print(
                code_block.get(
                    "code",
                    "",
                )
            )

    print("")
    print("写在最后：")
    print(
        article.get(
            "ending",
            "",
        )
    )

    print("")
    print("=" * 60)
    print("完整公众号文章打印结束")
    print("=" * 60)

    # --------------------------------------------------------
    # 10. 收集封面候选
    # --------------------------------------------------------

    cover_urls = collect_cover_urls(
        selected_news
    )

    # --------------------------------------------------------
    # 11. 下载真正的 JPEG 封面
    # --------------------------------------------------------

    download_cover(
        cover_urls
    )

    # --------------------------------------------------------
    # 12. 保存 article.json
    # --------------------------------------------------------

    with open(
        ARTICLE_FILE,
        "w",
        encoding="utf-8",
    ) as f:

        json.dump(
            article,
            f,
            ensure_ascii=False,
            indent=2,
        )

    print("")
    print("=" * 60)
    print("article.json 生成成功")
    print("=" * 60)

    print(
        f"文章标题："
        f"{article['title']}"
    )

    print(
        f"来源："
        f"{article['source']}"
    )

    print(
        f"原文："
        f"{article['original_link']}"
    )

    print(
        f"正文小节："
        f"{len(article['sections'])}"
    )

    total_code_blocks = sum(
        len(
            section.get(
                "code_blocks",
                [],
            )
        )
        for section in article["sections"]
    )

    print(
        f"代码示例："
        f"{total_code_blocks}"
    )

    print("")
    print("=" * 60)
    print("AI 新闻处理完成")
    print("=" * 60)


if __name__ == "__main__":
    main()
