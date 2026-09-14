import os
import json
import re
import mimetypes
import uuid
import urllib.request
import urllib.error


# ============================================================
# 微信公众号配置
# ============================================================

WECHAT_APP_ID = os.environ.get("WECHAT_APP_ID")
WECHAT_APP_SECRET = os.environ.get("WECHAT_APP_SECRET")

WECHAT_TOKEN_URL = (
    "https://api.weixin.qq.com/cgi-bin/token"
)

WECHAT_MATERIAL_UPLOAD_URL = (
    "https://api.weixin.qq.com/cgi-bin/material/add_material"
)

WECHAT_DRAFT_ADD_URL = (
    "https://api.weixin.qq.com/cgi-bin/draft/add"
)

ARTICLE_JSON_PATH = "article.json"

COVER_IMAGE_PATH = "cover.jpg"


# ============================================================
# HTTP JSON 请求
# ============================================================

def http_json_request(
    url,
    method="GET",
    data=None,
    timeout=60,
    headers=None
):

    request_headers = {
        "User-Agent": "AI-News-WeChat-Automation/1.0"
    }

    if headers:
        request_headers.update(headers)

    request = urllib.request.Request(
        url,
        data=data,
        headers=request_headers,
        method=method
    )

    try:

        with urllib.request.urlopen(
            request,
            timeout=timeout
        ) as response:

            response_data = response.read()

        return json.loads(
            response_data.decode("utf-8")
        )

    except urllib.error.HTTPError as e:

        error_body = ""

        try:
            error_body = e.read().decode(
                "utf-8",
                errors="replace"
            )
        except Exception:
            pass

        raise RuntimeError(
            f"微信公众号 HTTP 错误："
            f"{e.code}，"
            f"{error_body[:1000]}"
        )

    except urllib.error.URLError as e:

        raise RuntimeError(
            f"微信公众号网络错误：{e}"
        )

    except json.JSONDecodeError as e:

        raise RuntimeError(
            f"微信公众号返回的数据不是有效 JSON：{e}"
        )

    except Exception as e:

        raise RuntimeError(
            f"请求微信公众号接口失败：{e}"
        )


# ============================================================
# 获取 access_token
# ============================================================

def get_access_token():

    if not WECHAT_APP_ID:

        raise RuntimeError(
            "没有找到 WECHAT_APP_ID，请检查 GitHub Secrets。"
        )

    if not WECHAT_APP_SECRET:

        raise RuntimeError(
            "没有找到 WECHAT_APP_SECRET，请检查 GitHub Secrets。"
        )

    url = (
        f"{WECHAT_TOKEN_URL}"
        f"?grant_type=client_credential"
        f"&appid={WECHAT_APP_ID}"
        f"&secret={WECHAT_APP_SECRET}"
    )

    print(
        "正在请求微信公众号 access_token..."
    )

    result = http_json_request(
        url,
        method="GET",
        timeout=30
    )

    if "access_token" not in result:

        errcode = result.get(
            "errcode"
        )

        errmsg = result.get(
            "errmsg"
        )

        raise RuntimeError(
            f"微信公众号返回错误："
            f"errcode={errcode}, "
            f"errmsg={errmsg}"
        )

    access_token = result[
        "access_token"
    ]

    if not access_token:

        raise RuntimeError(
            "微信公众号返回的 access_token 为空。"
        )

    print(
        "========================================"
    )

    print(
        "微信公众号 API 连接成功！"
    )

    print(
        "AppID 已成功读取"
    )

    print(
        "AppSecret 已成功读取"
    )

    print(
        "access_token 已成功获取"
    )

    print(
        "========================================"
    )

    return access_token


# ============================================================
# 上传永久素材
# ============================================================

def upload_cover_image(
    access_token,
    image_path
):

    print(
        "\n========== 开始上传公众号封面 =========="
    )

    if not os.path.exists(image_path):

        raise RuntimeError(
            f"找不到封面图片：{image_path}"
        )

    if not os.path.isfile(image_path):

        raise RuntimeError(
            f"封面路径不是文件：{image_path}"
        )

    file_size = os.path.getsize(
        image_path
    )

    print(
        f"封面文件：{image_path}"
    )

    print(
        f"封面大小：{file_size} bytes"
    )

    content_type, _ = mimetypes.guess_type(
        image_path
    )

    if not content_type:

        content_type = "image/jpeg"

    filename = os.path.basename(
        image_path
    )

    boundary = (
        "----AI-News-WeChat-"
        + uuid.uuid4().hex
    )

    body = bytearray()

    body.extend(
        (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; '
            f'name="media"; '
            f'filename="{filename}"\r\n'
            f"Content-Type: {content_type}\r\n"
            f"\r\n"
        ).encode("utf-8")
    )

    with open(
        image_path,
        "rb"
    ) as image_file:

        body.extend(
            image_file.read()
        )

    body.extend(
        (
            f"\r\n"
            f"--{boundary}--\r\n"
        ).encode("utf-8")
    )

    url = (
        f"{WECHAT_MATERIAL_UPLOAD_URL}"
        f"?access_token={access_token}"
        f"&type=image"
    )

    result = http_json_request(
        url,
        method="POST",
        data=bytes(body),
        timeout=60,
        headers={
            "Content-Type": (
                f"multipart/form-data; "
                f"boundary={boundary}"
            )
        }
    )

    if "errcode" in result:

        raise RuntimeError(
            f"上传公众号封面失败："
            f"errcode={result.get('errcode')}, "
            f"errmsg={result.get('errmsg')}"
        )

    media_id = result.get(
        "media_id"
    )

    if not media_id:

        raise RuntimeError(
            "微信上传封面成功响应中没有 media_id。"
        )

    print(
        "公众号封面上传成功！"
    )

    print(
        f"thumb_media_id：{media_id}"
    )

    return media_id


# ============================================================
# Markdown → 微信公众号 HTML
# ============================================================

def escape_html(text):

    text = text.replace(
        "&",
        "&amp;"
    )

    text = text.replace(
        "<",
        "&lt;"
    )

    text = text.replace(
        ">",
        "&gt;"
    )

    return text


def convert_inline_markdown(text):

    # --------------------------------------------------------
    # 先保护 Markdown 链接
    # --------------------------------------------------------

    links = []

    def save_link(match):

        label = match.group(1)
        url = match.group(2)

        placeholder = (
            f"___WECHAT_LINK_{len(links)}___"
        )

        links.append(
            (placeholder, label, url)
        )

        return placeholder

    text = re.sub(
        r"\[([^\]]+)\]\((https?://[^)]+)\)",
        save_link,
        text
    )

    # --------------------------------------------------------
    # HTML 转义
    # --------------------------------------------------------

    text = escape_html(
        text
    )

    # --------------------------------------------------------
    # 加粗
    # --------------------------------------------------------

    text = re.sub(
        r"\*\*(.+?)\*\*",
        r"<strong>\1</strong>",
        text
    )

    text = re.sub(
        r"__(.+?)__",
        r"<strong>\1</strong>",
        text
    )

    # --------------------------------------------------------
    # 删除 Markdown 图片
    # --------------------------------------------------------

    text = re.sub(
        r"!\[[^\]]*\]\([^)]+\)",
        "",
        text
    )

    # --------------------------------------------------------
    # 普通 Markdown 链接
    # --------------------------------------------------------

    for placeholder, label, url in links:

        safe_label = escape_html(
            label
        )

        safe_url = escape_html(
            url
        )

        html_link = (
            f'<a href="{safe_url}">'
            f"{safe_label}"
            f"</a>"
        )

        text = text.replace(
            placeholder,
            html_link
        )

    return text


def markdown_to_wechat_html(markdown_text):

    if not markdown_text:

        return ""

    markdown_text = markdown_text.replace(
        "\r\n",
        "\n"
    )

    markdown_text = markdown_text.replace(
        "\r",
        "\n"
    )

    lines = markdown_text.split(
        "\n"
    )

    html_parts = []

    paragraph_lines = []

    def flush_paragraph():

        if not paragraph_lines:
            return

        paragraph = " ".join(
            line.strip()
            for line in paragraph_lines
            if line.strip()
        ).strip()

        paragraph_lines.clear()

        if not paragraph:
            return

        paragraph_html = (
            convert_inline_markdown(
                paragraph
            )
        )

        html_parts.append(
            f"<p>{paragraph_html}</p>"
        )

    for line in lines:

        stripped = line.strip()

        # ----------------------------------------------------
        # 空行
        # ----------------------------------------------------

        if not stripped:

            flush_paragraph()

            continue

        # ----------------------------------------------------
        # 分隔线
        # ----------------------------------------------------

        if re.fullmatch(
            r"[-*_]{3,}",
            stripped
        ):

            flush_paragraph()

            html_parts.append(
                "<hr>"
            )

            continue

        # ----------------------------------------------------
        # 一级标题
        # ----------------------------------------------------

        match = re.match(
            r"^#\s+(.+)$",
            stripped
        )

        if match:

            flush_paragraph()

            title = convert_inline_markdown(
                match.group(1)
            )

            html_parts.append(
                f"<h2>{title}</h2>"
            )

            continue

        # ----------------------------------------------------
        # 二级 / 三级标题
        # ----------------------------------------------------

        match = re.match(
            r"^#{2,6}\s+(.+)$",
            stripped
        )

        if match:

            flush_paragraph()

            title = convert_inline_markdown(
                match.group(1)
            )

            html_parts.append(
                f"<h3>{title}</h3>"
            )

            continue

        # ----------------------------------------------------
        # 无序列表
        # ----------------------------------------------------

        if re.match(
            r"^[-*+]\s+",
            stripped
        ):

            flush_paragraph()

            list_items = []

            while True:

                if not lines:
                    break

                break

            # 单行列表先按普通段落处理，
            # 避免复杂 Markdown 解析影响文章正文。
            stripped = re.sub(
                r"^[-*+]\s+",
                "",
                stripped
            )

            paragraph_lines.append(
                stripped
            )

            continue

        # ----------------------------------------------------
        # 普通段落
        # ----------------------------------------------------

        paragraph_lines.append(
            stripped
        )

    flush_paragraph()

    return "\n".join(
        html_parts
    )


# ============================================================
# 清理文章标题
# ============================================================

def clean_article_title(title):

    if not title:

        return "今日AI资讯"

    title = str(title).strip()

    title = re.sub(
        r"^#{1,6}\s*",
        "",
        title
    )

    title = title.strip()

    if len(title) > 64:

        title = title[:64].rstrip()

    return title or "今日AI资讯"


# ============================================================
# 读取 article.json
# ============================================================

def load_article():

    print(
        "\n========== 读取 AI 生成文章 =========="
    )

    if not os.path.exists(
        ARTICLE_JSON_PATH
    ):

        raise RuntimeError(
            f"找不到 {ARTICLE_JSON_PATH}。"
            "请确认 news_fetcher.py 已经成功执行。"
        )

    with open(
        ARTICLE_JSON_PATH,
        "r",
        encoding="utf-8"
    ) as file:

        try:

            article_data = json.load(
                file
            )

        except json.JSONDecodeError as e:

            raise RuntimeError(
                f"article.json 不是有效 JSON：{e}"
            )

    title = clean_article_title(
        article_data.get(
            "title",
            ""
        )
    )

    content = article_data.get(
        "content",
        ""
    )

    if not content:

        raise RuntimeError(
            "article.json 中 content 为空。"
        )

    print(
        f"文章标题：{title}"
    )

    print(
        f"Markdown 正文长度："
        f"{len(content)} 字符"
    )

    return {
        "title": title,
        "content": content,
        "source": article_data.get(
            "source",
            ""
        ),
        "link": article_data.get(
            "link",
            ""
        ),
        "pub_date": article_data.get(
            "pub_date",
            ""
        ),
        "generated_date": article_data.get(
            "generated_date",
            ""
        )
    }


# ============================================================
# 添加微信公众号草稿
# ============================================================

def add_draft(
    access_token,
    article,
    thumb_media_id
):

    print(
        "\n========== 开始创建微信公众号草稿 =========="
    )

    title = article["title"]

    markdown_content = article["content"]

    html_content = markdown_to_wechat_html(
        markdown_content
    )

    if not html_content:

        raise RuntimeError(
            "Markdown 转换后的 HTML 正文为空。"
        )

    # --------------------------------------------------------
    # 微信 draft/add 所需文章对象
    # --------------------------------------------------------

    article_data = {
        "title": title,
        "author": "AI新闻自动化",
        "digest": (
            f"每日 AI 新闻自动整理："
            f"{title}"
        ),
        "content": html_content,
        "content_source_url": article.get(
            "link",
            ""
        ),
        "thumb_media_id": thumb_media_id,
        "show_cover_pic": 1,
        "need_open_comment": 1,
        "only_fans_can_comment": 0
    }

    payload = {
        "articles": [
            article_data
        ]
    }

    data = json.dumps(
        payload,
        ensure_ascii=False
    ).encode("utf-8")

    url = (
        f"{WECHAT_DRAFT_ADD_URL}"
        f"?access_token={access_token}"
    )

    print(
        f"草稿标题：{title}"
    )

    print(
        f"HTML 正文长度："
        f"{len(html_content)} 字符"
    )

    result = http_json_request(
        url,
        method="POST",
        data=data,
        timeout=60,
        headers={
            "Content-Type": "application/json; charset=utf-8"
        }
    )

    if "errcode" in result:

        raise RuntimeError(
            f"创建微信公众号草稿失败："
            f"errcode={result.get('errcode')}, "
            f"errmsg={result.get('errmsg')}"
        )

    media_id = result.get(
        "media_id"
    )

    if not media_id:

        raise RuntimeError(
            "微信公众号草稿接口返回成功，"
            "但没有返回 media_id。"
        )

    print(
        "\n========================================"
    )

    print(
        "🎉 微信公众号草稿创建成功！"
    )

    print(
        f"草稿 media_id：{media_id}"
    )

    print(
        f"文章标题：{title}"
    )

    print(
        "现在可以进入微信公众号后台 → 草稿箱查看。"
    )

    print(
        "========================================"
    )

    return media_id


# ============================================================
# 主程序
# ============================================================

def main():

    print(
        "\n========================================"
    )

    print(
        "      微信公众号自动草稿系统启动"
    )

    print(
        "========================================"
    )

    # --------------------------------------------------------
    # 第一步：检查文章
    # --------------------------------------------------------

    article = load_article()

    # --------------------------------------------------------
    # 第二步：获取 access_token
    # --------------------------------------------------------

    access_token = get_access_token()

    # --------------------------------------------------------
    # 第三步：上传 cover.jpg
    # --------------------------------------------------------

    thumb_media_id = upload_cover_image(
        access_token,
        COVER_IMAGE_PATH
    )

    # --------------------------------------------------------
    # 第四步：创建公众号草稿
    # --------------------------------------------------------

    add_draft(
        access_token,
        article,
        thumb_media_id
    )

    print(
        "\n========================================"
    )

    print(
        "微信公众号自动化流程执行完成！"
    )

    print(
        "========================================"
    )


# ============================================================
# 程序入口
# ============================================================

if __name__ == "__main__":
    main()
