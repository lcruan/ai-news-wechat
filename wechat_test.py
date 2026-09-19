import os
import json
import re
import html
import urllib.request
import urllib.error
import urllib.parse


# ============================================================
# 基础配置
# ============================================================

WECHAT_APP_ID = os.environ.get("WECHAT_APP_ID")
WECHAT_APP_SECRET = os.environ.get("WECHAT_APP_SECRET")

WECHAT_API_BASE = "https://api.weixin.qq.com"

ARTICLE_FILE = "article.json"
PROCESSED_NEWS_FILE = "processed_news.json"
MAX_PROCESSED_NEWS = 200

# 你上传到 GitHub 仓库根目录的封面
COVER_IMAGE = "cover.jpg"


# ============================================================
# 微信 HTTP JSON 请求
# ============================================================

def http_json_request(
    url,
    method="GET",
    data=None,
    headers=None
):

    if headers is None:
        headers = {}

    request = urllib.request.Request(
        url,
        data=data,
        headers=headers,
        method=method
    )

    try:

        with urllib.request.urlopen(
            request,
            timeout=120
        ) as response:

            raw = response.read()

        result = json.loads(
            raw.decode(
                "utf-8",
                errors="ignore"
            )
        )

    except urllib.error.HTTPError as e:

        try:
            error_body = e.read().decode(
                "utf-8",
                errors="ignore"
            )
        except Exception:
            error_body = ""

        raise RuntimeError(
            f"微信 API HTTP 错误："
            f"{e.code} {error_body}"
        )

    except Exception as e:

        raise RuntimeError(
            f"微信 API 请求失败：{e}"
        )

    if isinstance(result, dict):

        errcode = result.get(
            "errcode",
            0
        )

        if errcode != 0:

            raise RuntimeError(
                "微信 API 返回错误："
                f"errcode={errcode}, "
                f"errmsg={result.get('errmsg')}"
            )

    return result


# ============================================================
# 获取 access_token
# ============================================================

def get_access_token():

    if not WECHAT_APP_ID:
        raise RuntimeError(
            "没有找到 WECHAT_APP_ID"
        )

    if not WECHAT_APP_SECRET:
        raise RuntimeError(
            "没有找到 WECHAT_APP_SECRET"
        )

    print("")
    print("=" * 50)
    print("开始获取微信公众号 access_token")
    print("=" * 50)

    url = (
        f"{WECHAT_API_BASE}"
        f"/cgi-bin/token"
        f"?grant_type=client_credential"
        f"&appid={urllib.parse.quote(WECHAT_APP_ID)}"
        f"&secret={urllib.parse.quote(WECHAT_APP_SECRET)}"
    )

    result = http_json_request(
        url
    )

    access_token = result.get(
        "access_token"
    )

    if not access_token:
        raise RuntimeError(
            "微信没有返回 access_token"
        )

    print(
        "access_token 获取成功！"
    )

    return access_token


# ============================================================
# HTML 转义
# ============================================================

def escape_text(text):

    if text is None:
        return ""

    return html.escape(
        str(text),
        quote=False
    )


# ============================================================
# 清洗章节标题
# ============================================================

def clean_section_heading(
    heading,
    number=None
):

    heading = str(
        heading or ""
    ).strip()

    if not heading:
        return ""

    # 去掉 Markdown 标题
    heading = re.sub(
        r"^#{1,6}\s*",
        "",
        heading
    ).strip()

    # 去掉开头的章节编号
    heading = re.sub(
        r"^\s*[（(]?\s*(?:0?[1-9]|1[0-9]|20)"
        r"\s*[)）]?\s*"
        r"(?:[：:、.．。\-—–])?\s*",
        "",
        heading
    ).strip()

    # 如果指定了当前编号，再做一次针对性清洗
    if number is not None:

        number_text = f"{number:02d}"

        heading = re.sub(
            rf"^\s*[（(]?{re.escape(number_text)}"
            rf"\s*[)）]?\s*"
            rf"(?:[：:、.．。\-—–])?\s*",
            "",
            heading
        ).strip()

        heading = re.sub(
            rf"^\s*[（(]?{number}"
            rf"\s*[)）]?\s*"
            rf"(?:[：:、.．。\-—–])?\s*",
            "",
            heading
        ).strip()

    # 去掉标题末尾括号式副标题
    heading = re.sub(
        r"\s*[（(][^（）()]{1,40}[）)]\s*$",
        "",
        heading
    ).strip()

    return heading


# ============================================================
# 清洗正文开头错误出现的章节编号
# ============================================================

def clean_section_paragraph(
    text,
    number
):

    text = str(
        text or ""
    ).strip()

    if not text:
        return ""

    number_text = f"{number:02d}"

    text = re.sub(
        rf"^{re.escape(number_text)}"
        r"\s*(?:[：:、.\-—–])?\s*",
        "",
        text
    ).strip()

    text = re.sub(
        rf"^{number}"
        r"\s*(?:[：:、.\-—–])?\s*",
        "",
        text
    ).strip()

    return text


# ============================================================
# Markdown 清洗
# ============================================================

def clean_inline_markdown(text):

    text = str(text or "")

    # Markdown 链接
    text = re.sub(
        r"\[([^\]]+)\]\([^)]+\)",
        r"\1",
        text
    )

    # 加粗
    text = re.sub(
        r"\*\*(.*?)\*\*",
        r"<strong>\1</strong>",
        text
    )

    # 单星号斜体
    text = re.sub(
        r"(?<!\*)\*([^*]+)\*(?!\*)",
        r"\1",
        text
    )

    # Markdown 标题
    text = re.sub(
        r"^#{1,6}\s*",
        "",
        text
    )

    # 裸 URL 删除
    text = re.sub(
        r"https?://\S+",
        "",
        text
    )

    return text.strip()


# ============================================================
# 普通段落
# ============================================================

def render_paragraph(text):

    text = str(text or "").strip()

    if not text:
        return ""

    placeholders = []

    def replace_bold(match):

        index = len(placeholders)

        placeholders.append(
            escape_text(
                match.group(1)
            )
        )

        return f"___BOLD_{index}___"

    text = re.sub(
        r"\*\*(.*?)\*\*",
        replace_bold,
        text
    )

    text = escape_text(
        text
    )

    for index, value in enumerate(
        placeholders
    ):

        text = text.replace(
            f"___BOLD_{index}___",
            f"<strong>{value}</strong>"
        )

    text = re.sub(
        r"\[([^\]]+)\]\([^)]+\)",
        r"\1",
        text
    )

    text = re.sub(
        r"(?<!\*)\*([^*]+)\*(?!\*)",
        r"\1",
        text
    )

    return (
        '<p style="'
        'margin:10px 0;'
        'font-size:14px;'
        'line-height:1.8em;'
        'letter-spacing:1px;'
        'color:#333333;'
        'width:100%;'
        'box-sizing:border-box;'
        'word-break:normal;'
        'overflow-wrap:normal;'
        '">'
        f"{text}"
        "</p>"
    )


# ============================================================
# 代码语言名称
# ============================================================

def clean_code_language(language):

    language = str(
        language or ""
    ).strip().lower()

    language_map = {
        "js": "JavaScript",
        "javascript": "JavaScript",

        "ts": "TypeScript",
        "typescript": "TypeScript",

        "jsx": "JSX",
        "tsx": "TSX",

        "vue": "Vue",

        "html": "HTML",
        "htm": "HTML",

        "css": "CSS",
        "scss": "SCSS",
        "sass": "Sass",
        "less": "Less",

        "json": "JSON",

        "xml": "XML",

        "bash": "Bash",
        "shell": "Shell",
        "sh": "Shell",

        "python": "Python",
        "py": "Python",

        "java": "Java",

        "c": "C",
        "cpp": "C++",
        "c++": "C++",

        "sql": "SQL",

        "go": "Go",

        "rust": "Rust",

        "php": "PHP",

        "text": "Text",
        "txt": "Text",
        "plaintext": "Text",
        "plain": "Text",
    }

    if language in language_map:
        return language_map[language]

    if not language:
        return "Code"

    return language[:20]


# ============================================================
# 代码安全渲染
#
# 重要：
#
# 这里不再做复杂的正则语法高亮。
#
# 原来的 highlight_code() 会：
#
# 1. HTML 转义
# 2. 加 token
# 3. 匹配数字
# 4. 匹配关键词
# 5. 匹配函数
# 6. 匹配操作符
# 7. 再恢复 token
#
# 多轮正则处理已经生成的 HTML，
# 很容易破坏 span 标签。
#
# 公众号文章首先必须保证代码内容准确、
# HTML 结构稳定。
#
# 所以现在：
#
# 原始代码
#     ↓
# HTML escape
#     ↓
# <pre><code>
#
# 完整保留。
#
# 不修改代码字符。
# 不改变缩进。
# 不改变换行。
# 不改变括号。
# 不改变 HTML 标签。
# 不改变 JS / TS / CSS 语法。
# ============================================================

def highlight_code(
    code,
    language
):

    code = str(
        code or ""
    )

    if not code:
        return ""

    # --------------------------------------------------------
    # 直接进行 HTML 转义。
    #
    # 例如：
    #
    # <div>
    #
    # 会变成：
    #
    # &lt;div&gt;
    #
    # 防止代码本身被浏览器当成真正 HTML。
    # --------------------------------------------------------

    return html.escape(
        code,
        quote=False
    )


# ============================================================
# 代码块
#
# 重点：
#
# PC：
# 正常显示完整代码。
#
# 手机：
# 超宽代码横向滚动。
#
# 不再强制：
#
# word-break:break-all
# overflow-wrap:break-word
# white-space:pre-wrap
#
# 因此：
#
# const myVariable = ...
#
# 不会被拆成：
#
# const myVari
# able = ...
#
# HTML：
#
# <div class="container">
#
# 也不会被任意拆开。
# ============================================================

def render_code_block(code_block):

    if not isinstance(
        code_block,
        dict
    ):
        return ""

    code = code_block.get(
        "code",
        ""
    )

    if code is None:
        code = ""

    code = str(
        code
    )

    if not code.strip():
        return ""

    language = clean_code_language(
        code_block.get(
            "language",
            ""
        )
    )

    caption = str(
        code_block.get(
            "caption",
            ""
        ) or ""
    ).strip()

    # --------------------------------------------------------
    # 安全代码渲染
    # --------------------------------------------------------

    safe_code = highlight_code(
        code,
        language
    )

    caption_html = ""

    if caption:

        caption = clean_inline_markdown(
            caption
        )

        caption = escape_text(
            caption
        )

        caption_html = f"""
<p style="
    margin:12px 0 6px 0;
    padding:0;
    font-size:13px;
    line-height:1.7em;
    color:#666666;
    width:100%;
    box-sizing:border-box;
">
    {caption}
</p>
""".strip()

    return f"""
{caption_html}

<section style="
    margin:16px 0 20px 0;
    padding:0;
    width:100%;
    box-sizing:border-box;
    border-radius:8px;
    overflow:hidden;
    background-color:#282c34;
    border:1px solid #3a3f4b;
">

    <!-- 代码块顶部栏 -->
    <section style="
        margin:0;
        padding:0 12px;
        height:34px;
        line-height:34px;
        background-color:#21252b;
        box-sizing:border-box;
        border-bottom:1px solid #3a3f4b;
    ">

        <span style="
            display:inline-block;
            width:8px;
            height:8px;
            margin-right:5px;
            border-radius:50%;
            background-color:#ff5f56;
            vertical-align:middle;
        "></span>

        <span style="
            display:inline-block;
            width:8px;
            height:8px;
            margin-right:5px;
            border-radius:50%;
            background-color:#ffbd2e;
            vertical-align:middle;
        "></span>

        <span style="
            display:inline-block;
            width:8px;
            height:8px;
            margin-right:10px;
            border-radius:50%;
            background-color:#27c93f;
            vertical-align:middle;
        "></span>

        <span style="
            font-size:11px;
            line-height:34px;
            color:#abb2bf;
            vertical-align:middle;
            letter-spacing:0.5px;
        ">
            {escape_text(language)}
        </span>

    </section>


    <!--
        代码滚动区域

        注意：
        这里允许横向滚动。
        不强制折行。
    -->
    <section style="
        margin:0;
        padding:0;
        width:100%;
        box-sizing:border-box;
        overflow-x:auto;
        overflow-y:hidden;
        -webkit-overflow-scrolling:touch;
    ">

        <pre style="
            margin:0;
            padding:15px 16px;
            width:max-content;
            min-width:100%;
            box-sizing:border-box;
            background-color:#282c34;
            color:#abb2bf;
            font-family:
                Menlo,
                Monaco,
                Consolas,
                'Courier New',
                monospace;
            font-size:13px;
            line-height:1.7em;
            letter-spacing:0;
            white-space:pre !important;
            word-break:normal !important;
            overflow-wrap:normal !important;
            tab-size:2;
        "><code style="
            margin:0;
            padding:0;
            background-color:transparent;
            color:#abb2bf;
            font-family:
                Menlo,
                Monaco,
                Consolas,
                'Courier New',
                monospace;
            font-size:13px;
            line-height:1.7em;
            white-space:pre !important;
            word-break:normal !important;
            overflow-wrap:normal !important;
            display:block;
            width:max-content;
            min-width:100%;
        ">{safe_code}</code></pre>

    </section>

</section>
""".strip()


# ============================================================
# 顶部导语框
# ============================================================

def render_lead(lead):

    lead = str(
        lead or ""
    ).strip()

    if not lead:
        return ""

    lead = clean_inline_markdown(
        lead
    )

    lead = escape_text(
        lead
    )

    return f"""
<section style="
    margin:10px auto 24px auto;
    padding:10px 15px;
    background-color:#f2f9ff;
    border:1px solid #5c8efe;
    box-sizing:border-box;
    position:relative;
    overflow:hidden;
">

    <section style="
        position:absolute;
        top:-1px;
        left:-1px;
        width:0;
        height:0;
        border-top:18px solid rgb(255,196,64);
        border-right:18px solid transparent;
        line-height:0;
        font-size:0;
    "></section>

    <p style="
        margin:0;
        font-size:14px;
        line-height:1.75em;
        letter-spacing:1.5px;
        color:#333333;
        width:100%;
        box-sizing:border-box;
        word-break:normal;
        overflow-wrap:normal;
    ">
        {lead}
    </p>

    <section style="
        position:absolute;
        right:-1px;
        bottom:-1px;
        width:0;
        height:0;
        border-bottom:18px solid #5c8efe;
        border-left:18px solid transparent;
        line-height:0;
        font-size:0;
    "></section>

</section>
""".strip()


# ============================================================
# 章节标题
# ============================================================

def render_section_heading(
    number,
    heading
):

    heading = clean_section_heading(
        heading,
        number
    )

    heading = escape_text(
        heading
    )

    number_text = f"{number:02d}"

    return f"""
<section style="
    margin:24px 0 16px 0;
    padding:0;
    display:flex;
    align-items:stretch;
    width:100%;
    box-sizing:border-box;
">

    <section style="
        width:60px;
        min-width:60px;
        height:30px;
        position:relative;
        box-sizing:border-box;
        background-color:#ebf6ff;
        overflow:hidden;
    ">

        <section style="
            position:absolute;
            left:0;
            top:0;
            width:50px;
            height:30px;
            background-color:#5c8efe;
            clip-path:polygon(
                0 0,
                100% 0,
                78% 50%,
                100% 100%,
                0 100%
            );
            box-sizing:border-box;
        "></section>

        <span style="
            position:absolute;
            left:0;
            top:0;
            width:40px;
            height:30px;
            line-height:30px;
            text-align:center;
            font-size:14px;
            font-weight:bold;
            color:#ffffff;
            z-index:2;
        ">
            {number_text}
        </span>

    </section>


    <section style="
        flex:1;
        min-width:0;
        height:30px;
        padding:0 12px;
        background-color:#ebf6ff;
        border-top:1px solid #5c8efe;
        border-bottom:1px solid #5c8efe;
        color:#5c8efe;
        font-size:16px;
        line-height:28px;
        font-weight:bold;
        box-sizing:border-box;
        overflow:hidden;
        white-space:nowrap;
        text-overflow:ellipsis;
    ">
        {heading}
    </section>


    <section style="
        width:25px;
        min-width:25px;
        height:30px;
        position:relative;
        box-sizing:border-box;
        overflow:hidden;
    ">
        <section style="
            position:absolute;
            right:0;
            top:0;
            width:0;
            height:0;
            border-top:15px solid rgb(255,196,64);
            border-bottom:15px solid transparent;
            border-left:15px solid transparent;
            line-height:0;
            font-size:0;
        "></section>
    </section>

</section>
""".strip()


# ============================================================
# 小标题
# ============================================================

def render_subsection(
    heading,
    paragraph
):

    heading = clean_inline_markdown(
        heading
    )

    heading = escape_text(
        heading
    )

    return f"""
<p style="
    margin:16px 0 8px 0;
    padding:0;
    font-size:15px;
    line-height:1.7em;
    font-weight:bold;
    color:#333333;
    width:100%;
    box-sizing:border-box;
">
    {heading}
</p>

{render_paragraph(paragraph)}
""".strip()


# ============================================================
# 一句话总结 / 金句
# ============================================================

def render_highlight(text):

    if not text:
        return ""

    text = clean_inline_markdown(
        text
    )

    text = escape_text(
        text
    )

    return f"""
<section style="
    margin:16px 0;
    padding:11px 14px;
    background-color:#f8fbff;
    box-sizing:border-box;
    width:100%;
">
    <p style="
        margin:0;
        font-size:14px;
        line-height:1.8em;
        color:#333333;
        width:100%;
        box-sizing:border-box;
    ">
        <strong>{text}</strong>
    </p>
</section>
""".strip()


# ============================================================
# 列表
# ============================================================

def render_list(items):

    if not items:
        return ""

    result = """
<ul style="
    margin:10px 0;
    padding-left:22px;
    font-size:14px;
    line-height:1.8em;
    color:#333333;
    width:100%;
    box-sizing:border-box;
">
"""

    for item in items:

        item = clean_inline_markdown(
            item
        )

        item = escape_text(
            item
        )

        result += f"""
<li style="
    margin:6px 0;
">
    <p style="
        margin:0;
        font-size:14px;
        line-height:1.8em;
        width:100%;
        box-sizing:border-box;
    ">
        {item}
    </p>
</li>
"""

    result += """
</ul>
"""

    return result.strip()


# ============================================================
# 单个章节
# ============================================================

def render_section(
    number,
    section
):

    html_parts = []

    html_parts.append(
        render_section_heading(
            number,
            section.get(
                "heading",
                ""
            )
        )
    )

    paragraphs = section.get(
        "paragraphs",
        []
    )

    for paragraph in paragraphs:

        paragraph = clean_section_paragraph(
            paragraph,
            number
        )

        paragraph_html = render_paragraph(
            paragraph
        )

        if paragraph_html:
            html_parts.append(
                paragraph_html
            )

    subsections = section.get(
        "subsections",
        []
    )

    for subsection in subsections:

        html_parts.append(
            render_subsection(
                subsection.get(
                    "heading",
                    ""
                ),
                subsection.get(
                    "paragraph",
                    ""
                )
            )
        )

    highlight = section.get(
        "highlight",
        ""
    )

    if highlight:

        html_parts.append(
            render_highlight(
                highlight
            )
        )

    items = section.get(
        "list",
        []
    )

    if items:

        html_parts.append(
            render_list(
                items
            )
        )

    code_blocks = section.get(
        "code_blocks",
        []
    )

    if isinstance(
        code_blocks,
        dict
    ):
        code_blocks = [
            code_blocks
        ]

    if isinstance(
        code_blocks,
        list
    ):

        for code_block in code_blocks:

            code_html = render_code_block(
                code_block
            )

            if code_html:
                html_parts.append(
                    code_html
                )

    return "\n".join(
        html_parts
    )


# ============================================================
# 处理 ending
# ============================================================

def normalize_ending(ending):

    if isinstance(
        ending,
        str
    ):

        ending = ending.strip()

        if not ending:
            return []

        paragraphs = re.split(
            r"\n+",
            ending
        )

        return [
            paragraph.strip()
            for paragraph in paragraphs
            if paragraph.strip()
        ]

    if not isinstance(
        ending,
        list
    ):

        if ending is None:
            return []

        text = str(
            ending
        ).strip()

        return [text] if text else []

    ending = [
        str(item).strip()
        for item in ending
        if str(item).strip()
    ]

    if not ending:
        return []

    if (
        len(ending) > 1
        and all(
            len(item) == 1
            for item in ending
        )
    ):

        return [
            "".join(ending)
        ]

    return ending


# ============================================================
# 微信公众号完整 HTML
# ============================================================

def build_wechat_html(article):

    title = escape_text(
        article.get(
            "title",
            ""
        )
    )

    lead = article.get(
        "lead",
        ""
    )

    sections = article.get(
        "sections",
        []
    )

    ending = article.get(
        "ending",
        []
    )

    source = escape_text(
        article.get(
            "source",
            ""
        )
    )

    original_link = escape_text(
        article.get(
            "original_link",
            ""
        )
    )

    html_parts = []

    html_parts.append(
        render_lead(
            lead
        )
    )

    for index, section in enumerate(
        sections[:4],
        start=1
    ):

        html_parts.append(
            render_section(
                index,
                section
            )
        )

    html_parts.append(
        render_section_heading(
            5,
            "写在最后"
        )
    )

    ending_paragraphs = normalize_ending(
        ending
    )

    for paragraph in ending_paragraphs:

        paragraph_html = render_paragraph(
            paragraph
        )

        if paragraph_html:
            html_parts.append(
                paragraph_html
            )

    html_parts.append(
        f"""
<section style="
    margin-top:28px;
    padding-top:12px;
    border-top:1px solid #eeeeee;
    width:100%;
    box-sizing:border-box;
">
    <p style="
        margin:6px 0;
        font-size:12px;
        line-height:1.7em;
        color:#999999;
        width:100%;
        box-sizing:border-box;
    ">
        <strong>来源：</strong>{source}
    </p>

    <p style="
        margin:6px 0;
        font-size:12px;
        line-height:1.7em;
        color:#999999;
        word-break:break-all;
        width:100%;
        box-sizing:border-box;
    ">
        <strong>原文：</strong>{original_link}
    </p>
</section>
""".strip()
    )

    body = "\n".join(
        part
        for part in html_parts
        if part
    )

    full_html = f"""
<div style="
    margin:0;
    padding:0;
    width:100%;
    box-sizing:border-box;
    font-family:-apple-system,BlinkMacSystemFont,
    'Helvetica Neue','PingFang SC',
    'Microsoft YaHei',Arial,sans-serif;
    color:#333333;
    font-size:14px;
    line-height:1.8em;
    letter-spacing:1px;
    word-break:normal;
    overflow-wrap:normal;
">
    {body}
</div>
""".strip()

    return full_html


# ============================================================
# 读取 article.json
# ============================================================

def load_article():

    if not os.path.exists(
        ARTICLE_FILE
    ):
        raise RuntimeError(
            f"找不到 {ARTICLE_FILE}"
        )

    with open(
        ARTICLE_FILE,
        "r",
        encoding="utf-8"
    ) as f:

        article = json.load(f)

    if not isinstance(
        article,
        dict
    ):
        raise RuntimeError(
            "article.json 格式错误"
        )

    return article


# ============================================================
# 上传封面图片
# ============================================================

def upload_cover_image(
    access_token
):

    print("")
    print("=" * 50)
    print("开始上传公众号封面")
    print("=" * 50)

    if not os.path.exists(
        COVER_IMAGE
    ):
        raise RuntimeError(
            f"找不到封面文件：{COVER_IMAGE}"
        )

    file_size = os.path.getsize(
        COVER_IMAGE
    )

    print(
        f"封面文件：{COVER_IMAGE}"
    )

    print(
        f"封面大小：{file_size} bytes"
    )

    url = (
        f"{WECHAT_API_BASE}"
        f"/cgi-bin/material/add_material"
        f"?access_token={access_token}"
        f"&type=image"
    )

    boundary = (
        "----WebKitFormBoundary"
        "AIWechatNews2026"
    )

    with open(
        COVER_IMAGE,
        "rb"
    ) as f:

        file_data = f.read()

    filename = os.path.basename(
        COVER_IMAGE
    )

    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; '
        f'name="media"; filename="{filename}"\r\n'
        f"Content-Type: image/jpeg\r\n"
        f"\r\n"
    ).encode("utf-8")

    body += file_data

    body += (
        f"\r\n--{boundary}--\r\n"
    ).encode("utf-8")

    result = http_json_request(
        url,
        method="POST",
        data=body,
        headers={
            "Content-Type":
                f"multipart/form-data; boundary={boundary}"
        }
    )

    media_id = result.get(
        "media_id"
    )

    if not media_id:
        raise RuntimeError(
            "封面上传成功但没有返回 media_id"
        )

    print(
        "公众号封面上传成功！"
    )

    print(
        f"thumb_media_id：{media_id}"
    )

    return media_id


# ============================================================
# 记录已经成功进入微信公众号草稿箱的文章
# ============================================================

def record_processed_news(article):

    link = str(
        article.get(
            "original_link",
            "",
        )
        or ""
    ).strip()

    if not link:
        print(
            "警告：文章没有 original_link，"
            "无法记录已处理状态。"
        )
        return

    links = []

    if os.path.exists(
        PROCESSED_NEWS_FILE
    ):
        try:

            with open(
                PROCESSED_NEWS_FILE,
                "r",
                encoding="utf-8",
            ) as f:

                data = json.load(f)

            if isinstance(
                data,
                dict
            ):
                links = data.get(
                    "links",
                    []
                )

            elif isinstance(
                data,
                list
            ):
                links = data

        except Exception as e:

            print(
                "读取已处理文章记录失败，将重新建立记录：",
                str(e)
            )

    links = [
        str(item).strip()
        for item in links
        if str(item).strip()
    ]

    if link not in links:
        links.append(link)

    links = links[
        -MAX_PROCESSED_NEWS:
    ]

    with open(
        PROCESSED_NEWS_FILE,
        "w",
        encoding="utf-8",
    ) as f:

        json.dump(
            {"links": links},
            f,
            ensure_ascii=False,
            indent=2,
        )

    print(
        f"已记录处理文章：{link}"
    )

    print(
        f"累计已处理文章：{len(links)} 篇"
    )


# ============================================================
# 创建微信公众号草稿
# ============================================================

def add_draft(
    access_token,
    article,
    thumb_media_id
):

    print("")
    print("=" * 50)
    print("开始创建微信公众号草稿")
    print("=" * 50)

    title = str(
        article.get(
            "title",
            ""
        )
    ).strip()

    title = re.sub(
        r"\*\*(.*?)\*\*",
        r"\1",
        title
    )

    content = build_wechat_html(
        article
    )

    print(
        f"草稿标题：{title}"
    )

    print(
        f"HTML 正文长度：{len(content)} 字符"
    )

    payload = {
        "articles": [
            {
                "title": title,

                "author": "web前端开发之旅",

                "digest": (
                    article.get(
                        "lead",
                        ""
                    )[:120]
                ),

                "content": content,

                "content_source_url": (
                    article.get(
                        "original_link",
                        ""
                    )
                ),

                "thumb_media_id":
                    thumb_media_id,

                "show_cover_pic": 1,

                "need_open_comment": 1,

                "only_fans_can_comment": 0
            }
        ]
    }

    data = json.dumps(
        payload,
        ensure_ascii=False
    ).encode("utf-8")

    url = (
        f"{WECHAT_API_BASE}"
        f"/cgi-bin/draft/add"
        f"?access_token={access_token}"
    )

    result = http_json_request(
        url,
        method="POST",
        data=data,
        headers={
            "Content-Type":
                "application/json; charset=utf-8"
        }
    )

    media_id = result.get(
        "media_id"
    )

    if not media_id:
        raise RuntimeError(
            "草稿创建成功响应中没有 media_id"
        )

    print("")
    print("=" * 50)
    print("🎉 微信公众号草稿创建成功！")

    print(
        f"草稿 media_id：{media_id}"
    )

    print(
        f"文章标题：{title}"
    )

    print(
        "现在可以进入微信公众号后台 → 草稿箱查看。"
    )

    print("=" * 50)

    # 只有 draft/add 真正成功后，
    # 才把原文链接写入已处理记录。
    record_processed_news(
        article
    )

    return media_id


# ============================================================
# 主程序
# ============================================================

def main():

    print("")
    print("=" * 70)
    print("微信公众号自动化流程开始")
    print("=" * 70)

    # 1. 读取 AI 生成的文章
    article = load_article()

    print("")
    print(
        f"读取文章成功：{article.get('title', '')}"
    )

    # 2. 获取 access_token
    access_token = get_access_token()

    # 3. 上传封面
    thumb_media_id = upload_cover_image(
        access_token
    )

    # 4. 创建草稿
    add_draft(
        access_token,
        article,
        thumb_media_id
    )

    print("")
    print("=" * 70)
    print("微信公众号自动化流程执行完成！")
    print("=" * 70)


if __name__ == "__main__":
    main()
