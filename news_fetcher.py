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


# ============================================================
# 新闻源
# ============================================================

# 当前阶段只使用 DEV.to。
# 公众号定位以 Web 前端技术为主，重点关注 Vue、TypeScript、JavaScript、React、CSS、Vite、Web 性能等。
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

    articles = json.loads(data.decode("utf-8"))

    results = []

    for item in articles[:MAX_NEWS_PER_SOURCE]:

        article_id = item.get("id")
        title = clean_text(item.get("title", ""))
        description = clean_text(item.get("description", ""))
        link = normalize_url(item.get("url", ""))
        published_at = item.get("published_at", "")

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

        # 当前公众号定位明确以 Web 前端为主。
        # 只保留能从标题/摘要中确认与前端相关的文章，
        # 不再因为“AI”单独出现就把 AI-only 文章筛进来。
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
            "cover_image": normalize_url(cover_image),
            "social_image": normalize_url(
                item.get("social_image", "")
            ),
        })

    print(f"DEV.to {tag} 有效文章：{len(results)}")

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
    article = json.loads(data.decode("utf-8"))

    body_markdown = str(
        article.get("body_markdown", "")
        or ""
    ).strip()

    body_html = str(
        article.get("body_html", "")
        or ""
    ).strip()

    # 优先使用 DEV.to 返回的 Markdown 正文，
    # 因为它比 description 包含更多原文信息。
    source_content = body_markdown

    if not source_content:
        source_content = clean_text(body_html)

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
        f"DEV.to 完整正文长度：{len(source_content)} 字符"
    )

    return {
        "source_content": truncate_text(
            source_content,
            MAX_SOURCE_ARTICLE_CHARS,
        ),
        "cover_image": cover_image,
        "social_image": normalize_url(
            article.get("social_image", "")
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

            if image_url.startswith("http://") or image_url.startswith("https://"):
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

    payload = {
        "model": MODEL,
        "messages": messages,
        "temperature": 0.2,
        "max_tokens": max_tokens,
        "enable_thinking": False,
    }

    body = json.dumps(
        payload,
        ensure_ascii=False,
    ).encode("utf-8")

    for attempt in range(1, MAX_RETRIES + 1):

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
                "Authorization": (
                    "Bearer "
                    + SILICONFLOW_API_KEY
                ),
            },
            method="POST",
        )

        try:

            with urllib.request.urlopen(
                request,
                timeout=REQUEST_TIMEOUT,
            ) as response:

                response_data = response.read()

            result = json.loads(
                response_data.decode("utf-8")
            )

            choices = result.get("choices")

            if not choices:
                raise RuntimeError(
                    "SiliconFlow 返回结果中没有 choices"
                )

            message = choices[0].get("message", {})

            content = message.get("content", "")

            if not content:
                raise RuntimeError(
                    "SiliconFlow 返回内容为空"
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

            print(error_body[:1000])

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

            time.sleep(RETRY_WAIT_SECONDS)

    raise RuntimeError(
        f"SiliconFlow 连续 {MAX_RETRIES} 次请求失败"
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
        text = text[start:end + 1]

    return text


# ============================================================
# AI 筛选
# ============================================================

def ai_select_news(news_list):

    if not news_list:
        raise RuntimeError(
            "没有可供 AI 筛选的新闻"
        )

    compact_news = []

    for index, item in enumerate(news_list):

        compact_news.append({
            "id": index,
            "source": item.get("source", ""),
            "title": item.get("title", ""),
            "summary": truncate_text(
                item.get("summary", ""),
                MAX_SCREENING_SUMMARY_CHARS,
            ),
            "link": item.get("link", ""),
            "pubDate": item.get("pubDate", ""),
        })

    context = json.dumps(
        compact_news,
        ensure_ascii=False,
    )

    if len(context) > MAX_SCREENING_CONTEXT_CHARS:
        context = context[:MAX_SCREENING_CONTEXT_CHARS]

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
3. 优先选择真正的 Web 前端技术内容，尤其是 Vue、TypeScript、JavaScript、React、CSS、Vite、Web 性能、前端工程化等。
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

    result = call_ai([
        {
            "role": "user",
            "content": prompt,
        }
    ], max_tokens=1200)

    result = extract_json_from_ai(result)

    data = json.loads(result)

    selected_id = int(
        data.get("selected_id", 0)
    )

    if selected_id < 0 or selected_id >= len(news_list):
        raise RuntimeError(
            f"AI 返回的 selected_id 无效：{selected_id}"
        )

    selected = news_list[selected_id].copy()

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
# AI 生成公众号文章
# ============================================================

def ai_generate_article(news):

    source = news.get("source", "")
    title = news.get("title", "")
    summary = news.get("summary", "")
    source_content = news.get("source_content", "")
    link = news.get("link", "")
    pub_date = news.get("pubDate", "")

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
你是一名中文科技公众号编辑。

请根据下面提供的唯一一篇 DEV.to 英文技术文章原文，
写成一篇完整的中文微信公众号文章。

公众号名称：

web前端开发之旅

文章不是新闻列表，也不是资料汇总。

必须围绕这一篇文章，
写成一篇完整、连贯、适合微信公众号阅读的文章。

文章结构：

1. 一个有吸引力但不过度夸张的标题
2. 开场导语
3. 3～4 个正文小节
4. 每个小节由自然段组成
5. 最后有一个“写在最后”的总结

写作风格：

- 中文自然
- 清晰
- 技术感
- 有解释性
- 不要有明显 AI 腔
- 不要堆砌新闻事实
- 不要把文章写成新闻列表
- 不要重复同一个观点
- 段落之间要有自然过渡
- 重点技术概念可以使用加粗 Markdown，例如 **React**
- 不要使用表格
- 不要使用 emoji

最重要的事实约束：

你只能使用下面提供的信息，尤其是 source_content 中的原文内容。
不要把你自己的知识当成原文事实。

禁止：

- 编造人物
- 编造公司
- 编造数字
- 编造性能数据
- 编造 benchmark
- 编造技术细节
- 编造发布时间
- 编造专家观点
- 编造用户反馈
- 编造测试结果
- 编造因果关系
- 根据自己的知识补充原文没有提供的事实

如果资料中没有某个信息，就不要写。

不要使用：

“据报道”
“业内人士认为”
“这意味着”
“有望”
“值得注意的是”

除非这些内容能够直接从提供的事实中得到支持。

文章必须忠于原文提供的信息。

来源信息：

{json.dumps(
    fact_context,
    ensure_ascii=False,
    indent=2
)}

请严格返回 JSON，不要返回 Markdown 代码块：

{{
  "title": "文章标题",
  "lead": "开场导语",
  "sections": [
    {{
      "heading": "小节标题",
      "paragraphs": [
        "第一段",
        "第二段"
      ]
    }}
  ],
  "ending": "写在最后的总结"
}}
"""

    result = call_ai([
        {
            "role": "user",
            "content": prompt,
        }
    ], max_tokens=5000)

    result = extract_json_from_ai(result)

    article = json.loads(result)

    title = clean_text(
        article.get("title", "")
    )

    lead = clean_text(
        article.get("lead", "")
    )

    sections = article.get(
        "sections",
        [],
    )

    ending = clean_text(
        article.get("ending", "")
    )

    if not title:
        raise RuntimeError(
            "AI 生成的文章缺少 title"
        )

    if not lead:
        raise RuntimeError(
            "AI 生成的文章缺少 lead"
        )

    if not isinstance(sections, list):
        raise RuntimeError(
            "AI 生成的 sections 格式错误"
        )

    cleaned_sections = []

    for section in sections[:4]:

        if not isinstance(section, dict):
            continue

        heading = clean_text(
            section.get("heading", "")
        )

        paragraphs = section.get(
            "paragraphs",
            [],
        )

        if not heading:
            continue

        cleaned_paragraphs = []

        if isinstance(paragraphs, list):

            for paragraph in paragraphs:

                paragraph = clean_text(
                    str(paragraph)
                )

                if paragraph:
                    cleaned_paragraphs.append(
                        paragraph
                    )

        if cleaned_paragraphs:
            cleaned_sections.append({
                "heading": heading,
                "paragraphs": cleaned_paragraphs,
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

        link = item.get("link", "").strip()

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
    """
    判断文件内容是否是真正的 JPEG。

    不能只看 .jpg 后缀。
    微信判断的是实际文件内容。
    """

    if not data:
        return False

    return data.startswith(b"\xff\xd8\xff")


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

    # --------------------------------------------------------
    # 先检查仓库中原来的 cover.jpg
    # --------------------------------------------------------

    existing_cover = None

    if os.path.exists(COVER_FILE):

        try:

            with open(
                COVER_FILE,
                "rb",
            ) as f:
                existing_cover = f.read()

            if is_jpeg(existing_cover):

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

    # --------------------------------------------------------
    # 去重图片 URL
    # --------------------------------------------------------

    urls = []

    for url in image_urls:

        url = normalize_image_url(url)

        if not url:
            continue

        if url not in urls:
            urls.append(url)

    print(
        f"候选封面图片：{len(urls)} 个"
    )

    # --------------------------------------------------------
    # 逐个尝试
    # --------------------------------------------------------

    for index, image_url in enumerate(urls, 1):

        print("")
        print(
            f"尝试下载封面 "
            f"{index}/{len(urls)}："
        )

        print(image_url)

        try:

            # DEV.to 的 media2 图片代理经常会把 format=auto 返回成 WebP。
            # 微信封面这里最终必须使用真正的 JPEG，因此优先请求 JPEG 格式。
            request_url = image_url
            if (
                "media2.dev.to" in request_url
                and "format=auto" in request_url
            ):
                request_url = request_url.replace(
                    "format=auto",
                    "format=jpg",
                    1,
                )
                print("检测到 DEV.to 图片代理的 format=auto")
                print("改为请求 JPEG：")
                print(request_url)

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
                f"图片大小：{len(data)} bytes"
            )

            print(
                f"Content-Type：{content_type}"
            )

            # ------------------------------------------------
            # 关键：
            # 微信封面最终必须是真正的 JPEG。
            #
            # 如果 DEV.to 的图片代理仍然返回 WebP，
            # 就跳过当前地址，继续尝试其他候选图片。
            # ------------------------------------------------

            if not is_jpeg(data):

                print(
                    "跳过：文件内容不是 JPEG"
                )

                continue

            # ------------------------------------------------
            # 如果 Content-Type 明确说是非 JPEG，
            # 同样跳过。
            # ------------------------------------------------

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

            # ------------------------------------------------
            # 保存真正的 JPEG
            # ------------------------------------------------

            with open(
                COVER_FILE,
                "wb",
            ) as f:
                f.write(data)

            # 再验证一次
            with open(
                COVER_FILE,
                "rb",
            ) as f:
                saved_data = f.read()

            if not is_jpeg(saved_data):

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
                f"最终文件：{COVER_FILE}"
            )

            print(
                f"文件大小：{len(saved_data)} bytes"
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

    # --------------------------------------------------------
    # 所有来源图片都失败
    # 使用仓库中已有的有效 JPEG
    # --------------------------------------------------------

    if existing_cover is not None:

        with open(
            COVER_FILE,
            "wb",
        ) as f:
            f.write(existing_cover)

        print("")
        print(
            "没有找到可用的 JPEG 来源图片。"
        )

        print(
            "已使用仓库中的固定 cover.jpg 作为备用封面。"
        )

        return True

    # --------------------------------------------------------
    # 连备用封面都没有
    # 直接失败。
    #
    # 不能再生成一个 PNG/WebP 然后伪装成 JPG。
    # --------------------------------------------------------

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
        urls.append(cover_image)

    # DEV.to 可能有多个图片字段
    for key in [
        "social_image",
        "cover_image",
    ]:

        value = news.get(key, "")

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

            all_news.extend(news)

        except Exception as e:

            print("")
            print(
                f"DEV.to {tag} 抓取失败："
            )

            print(str(e))

    print("")
    print("=" * 60)
    print(
        f"原始新闻数量：{len(all_news)}"
    )
    print("=" * 60)

    # --------------------------------------------------------
    # 3. 去重
    # --------------------------------------------------------

    all_news = deduplicate_news(
        all_news
    )

    print(
        f"URL 去重后：{len(all_news)}"
    )

    # --------------------------------------------------------
    # 4. 关键词过滤
    # --------------------------------------------------------

    all_news = filter_news(
        all_news
    )

    print(
        f"关键词过滤后：{len(all_news)}"
    )

    if not all_news:

        raise RuntimeError(
            "没有找到符合条件的新闻"
        )

    # --------------------------------------------------------
    # 5. AI 筛选
    # --------------------------------------------------------

    selected_news = ai_select_news(
        all_news
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
        selected_news.get("id")
    )

    selected_news["source_content"] = detail.get(
        "source_content",
        "",
    )

    # 如果列表接口没有提供封面，则使用详情接口里的封面。
    if detail.get("cover_image"):
        selected_news["cover_image"] = detail.get(
            "cover_image"
        )

    if detail.get("social_image"):
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
    print(f"标题：{article.get('title', '')}")

    print("")
    print("导语：")
    print(article.get("lead", ""))

    for index, section in enumerate(
        article.get("sections", []),
        1,
    ):
        print("")
        print(f"{index:02d}｜{section.get('heading', '')}")

        for paragraph in section.get("paragraphs", []):
            print("")
            print(paragraph)

    print("")
    print("写在最后：")
    print(article.get("ending", ""))

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
        f"文章标题：{article['title']}"
    )

    print(
        f"来源：{article['source']}"
    )

    print(
        f"原文：{article['original_link']}"
    )

    print(
        f"正文小节：{len(article['sections'])}"
    )

    print("")
    print("=" * 60)
    print("AI 新闻处理完成")
    print("=" * 60)


if __name__ == "__main__":
    main()
