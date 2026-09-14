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
# Markdown 清洗
# ============================================================

def clean_inline_markdown(text):

    text = str(text or "")

    # Markdown 链接：
    # [文字](https://xxx)
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
# 处理普通段落中的加粗
# ============================================================

def render_paragraph(text):

    text = str(text or "").strip()

    if not text:
        return ""

    # 先保护 Markdown 加粗
    placeholders = []

    def replace_bold(match):

        index = len(placeholders)

        placeholders.append(
            escape_text(
                match.group(1)
            )
        )

        return (
            f"___BOLD_{index}___"
        )

    text = re.sub(
        r"\*\*(.*?)\*\*",
        replace_bold,
        text
    )

    # 普通文本 HTML 转义
    text = escape_text(
        text
    )

    # 恢复加粗
    for index, value in enumerate(
        placeholders
    ):

        text = text.replace(
            f"___BOLD_{index}___",
            f"<strong>{value}</strong>"
        )

    # 清理 Markdown
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
        '">'
        f"{text}"
        "</p>"
    )


# ============================================================
# 顶部导语框
# ============================================================

def render_lead(lead):

    lead = str(lead or "").strip()

    if not lead:
        return ""

    lead_html = render_paragraph(
        lead
    )

    # 去掉 render_paragraph 外层 p
    lead_html = re.sub(
        r'^<p[^>]*>',
        "",
        lead_html
    )

    lead_html = re.sub(
        r'</p>$',
        "",
        lead_html
    )

    return f"""
<section style="
    margin:10px auto;
    padding:10px 15px;
    background-color:rgb(242,249,255);
    border:1px solid rgb(80,132,249);
    box-sizing:border-box;
    position:relative;
">
    <section style="
        width:28px;
        height:3px;
        background-color:rgb(80,132,249);
        margin-bottom:8px;
    "></section>

    <p style="
        margin:0;
        font-size:14px;
        line-height:1.75em;
        letter-spacing:1.5px;
        color:rgb(51,51,51);
    ">
        {lead_html}
    </p>

    <section style="
        width:28px;
        height:3px;
        background-color:rgb(80,132,249);
        margin-left:auto;
        margin-top:8px;
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

    heading = escape_text(
        heading
    )

    return f"""
<section style="
    margin:24px 0 16px 0;
    display:flex;
    align-items:stretch;
    box-sizing:border-box;
">
    <section style="
        width:32px;
        min-width:32px;
        height:32px;
        line-height:30px;
        text-align:center;
        font-size:14px;
        font-weight:bold;
        color:rgb(80,132,249);
        background-color:rgb(242,249,255);
        border:1px solid rgb(80,132,249);
        box-sizing:border-box;
    ">
        {number:02d}
    </section>

    <section style="
        flex:1;
        margin-left:8px;
        min-height:32px;
        padding:5px 10px;
        background-color:rgb(242,249,255);
        border:1px solid rgb(80,132,249);
        color:rgb(80,132,249);
        font-size:16px;
        line-height:1.5em;
        font-weight:bold;
        box-sizing:border-box;
    ">
        {heading}
    </section>

    <section style="
        width:8px;
        min-width:8px;
        height:32px;
        margin-left:4px;
        background-color:rgb(80,132,249);
    "></section>
</section>
""".strip()


# ============================================================
# 小标题
# ============================================================

def render_subsection(
    heading,
    paragraph
):

    heading = escape_text(
        heading
    )

    return f"""
<p style="
    margin:16px 0 8px 0;
    font-size:15px;
    line-height:1.7em;
    font-weight:bold;
    color:#333333;
">
    {heading}
</p>

{render_paragraph(paragraph)}
""".strip()


# ============================================================
# 金句
# ============================================================

def render_highlight(text):

    if not text:
        return ""

    text = escape_text(
        text
    )

    return f"""
<section style="
    margin:16px 0;
    padding:10px 12px;
    background-color:rgb(248,251,255);
    border-left:4px solid rgb(80,132,249);
    box-sizing:border-box;
">
    <p style="
        margin:0;
        font-size:14px;
        line-height:1.8em;
        color:#333333;
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
">
"""

    for item in items:

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

    return "\n".join(
        html_parts
    )


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

    # --------------------------------------------------------
    # 导语
    # --------------------------------------------------------

    html_parts.append(
        render_lead(
            lead
        )
    )

    # --------------------------------------------------------
    # 01～04
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # 05 写在最后
    # --------------------------------------------------------

    html_parts.append(
        render_section_heading(
            5,
            "写在最后"
        )
    )

    for paragraph in ending:

        paragraph_html = render_paragraph(
            paragraph
        )

        if paragraph_html:
            html_parts.append(
                paragraph_html
            )

    # --------------------------------------------------------
    # 来源
    # --------------------------------------------------------

    html_parts.append(
        f"""
<section style="
    margin-top:28px;
    padding-top:12px;
    border-top:1px solid #eeeeee;
">
    <p style="
        margin:6px 0;
        font-size:12px;
        line-height:1.7em;
        color:#999999;
    ">
        <strong>来源：</strong>{source}
    </p>

    <p style="
        margin:6px 0;
        font-size:12px;
        line-height:1.7em;
        color:#999999;
        word-break:break-all;
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

    # 微信图文内容
    full_html = f"""
<div style="
    margin:0;
    padding:0;
    font-family:-apple-system,BlinkMacSystemFont,
    'Helvetica Neue','PingFang SC',
    'Microsoft YaHei',Arial,sans-serif;
    color:#333333;
    font-size:14px;
    line-height:1.8em;
    letter-spacing:1px;
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

    # 最后保险：
    # 防止 AI 标题残留 Markdown **
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

                "author": "web前端漫游记",

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
