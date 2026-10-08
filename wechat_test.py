import os
import json
import re
import html
import urllib.request
import urllib.error
import urllib.parse
import tempfile

from PIL import Image, ImageDraw, ImageFont
from pygments import lex
from pygments.lexers import get_lexer_by_name, TextLexer
from pygments.token import Token


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
#
# 防止 AI 自己把 01 / 02 / 03 / 04 写进标题。
# 编号统一由 Python 排版组件负责。
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
    #
    # 支持：
    # 01 标题
    # 01：标题
    # 01 - 标题
    # 01 — 标题
    # 01. 标题
    # 01、标题
    #
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

    # 章节标题不需要额外的括号式副标题。
    # 例如：
    # “带类型泛型的 as 组件（强类型安全）”
    # 统一保留为：
    # “带类型泛型的 as 组件”
    heading = re.sub(
        r"\s*[（(][^（）()]{1,40}[）)]\s*$",
        "",
        heading
    ).strip()

    return heading


# ============================================================
# 清洗正文开头错误出现的章节编号
#
# 例如：
# 01 近日，社交平台……
#
# 自动变成：
# 近日，社交平台……
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

    # 只处理正文最开始的编号
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

    # 清理 Markdown 链接
    text = re.sub(
        r"\[([^\]]+)\]\([^)]+\)",
        r"\1",
        text
    )

    # 清理单星号
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
#
# 将 AI 返回的语言名称统一成公众号中显示的名称。
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
# 代码图片生成与上传
#
# 微信移动端对 <pre><code> 的兼容性不稳定。
# 因此这里不再把代码作为 HTML 代码块发送，
# 而是由 Python 直接把“原文代码”渲染成 PNG 图片，
# 再上传到微信公众号正文图片接口。
#
# 注意：
# - code 内容不会被修改
# - AI 不负责重新生成代码
# - 没有原文代码时不会进入这里
# ============================================================

CODE_FONT_PATH = "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"
CODE_FONT_SIZE = 24
CODE_LINE_HEIGHT = 38
CODE_IMAGE_WIDTH = 1200
CODE_HORIZONTAL_PADDING = 28
CODE_VERTICAL_PADDING = 22
CODE_HEADER_HEIGHT = 58
CODE_MAX_LINES_PER_IMAGE = 55


def get_code_font(size=CODE_FONT_SIZE):

    candidates = [
        CODE_FONT_PATH,
        "/usr/share/fonts/truetype/noto/NotoSansMono-Regular.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf",
    ]

    for path in candidates:
        if os.path.exists(path):
            return ImageFont.truetype(path, size=size)

    return ImageFont.load_default()


def code_token_color(token_type):
    """把 Pygments token 映射成固定的代码图片颜色。"""

    if token_type in Token.Keyword:
        return "#C586C0"
    if token_type in Token.Name.Function:
        return "#DCDCAA"
    if token_type in Token.Name.Class:
        return "#4EC9B0"
    if token_type in Token.Name:
        return "#9CDCFE"
    if token_type in Token.String:
        return "#CE9178"
    if token_type in Token.Number:
        return "#B5CEA8"
    if token_type in Token.Comment:
        return "#6A9955"
    if token_type in Token.Operator:
        return "#D4D4D4"
    if token_type in Token.Punctuation:
        return "#D4D4D4"
    if token_type in Token.Generic:
        return "#D4D4D4"

    return "#D4D4D4"


def get_code_lexer(language):

    language = str(language or "text").strip().lower()

    lexer_map = {
        "javascript": "javascript",
        "typescript": "typescript",
        "jsx": "jsx",
        "tsx": "tsx",
        "vue": "html",
        "html": "html",
        "css": "css",
        "scss": "scss",
        "sass": "sass",
        "less": "less",
        "json": "json",
        "xml": "xml",
        "bash": "bash",
        "shell": "bash",
        "python": "python",
        "java": "java",
        "c": "c",
        "c++": "cpp",
        "sql": "sql",
        "go": "go",
        "rust": "rust",
        "php": "php",
        "markdown": "markdown",
        "yaml": "yaml",
        "text": "text",
    }

    lexer_name = lexer_map.get(language, "text")

    try:
        if lexer_name == "text":
            return TextLexer()
        return get_lexer_by_name(lexer_name)
    except Exception:
        return TextLexer()


def split_code_lines(code, font, draw):
    """仅为了图片宽度进行视觉换行，不修改 article.json 中的原始 code。"""

    max_width = CODE_IMAGE_WIDTH - CODE_HORIZONTAL_PADDING * 2
    result = []

    for line in str(code or "").replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if line == "":
            result.append("")
            continue

        current = ""
        for char in line:
            test = current + char
            bbox = draw.textbbox((0, 0), test, font=font)
            width = bbox[2] - bbox[0]
            if current and width > max_width:
                result.append(current)
                current = char
            else:
                current = test

        result.append(current)

    return result


def draw_highlighted_code(image, code, language, start_line, end_line, font):
    """把指定代码行绘制到图片上，代码文字本身保持原样。"""

    draw = ImageDraw.Draw(image)
    lexer = get_code_lexer(language)
    source_lines = str(code or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    selected_lines = source_lines[start_line:end_line]

    y = CODE_HEADER_HEIGHT + CODE_VERTICAL_PADDING
    x0 = CODE_HORIZONTAL_PADDING
    line_height = CODE_LINE_HEIGHT

    # Pygments token 流按字符累计，再根据换行分配到当前视觉行。
    tokens_by_line = [[]]
    for token_type, value in lex("\n".join(selected_lines), lexer):
        parts = value.split("\n")
        for index, part in enumerate(parts):
            if index > 0:
                tokens_by_line.append([])
            if part:
                tokens_by_line[-1].append((token_type, part))

    for line_index, tokens in enumerate(tokens_by_line):
        if line_index >= len(selected_lines):
            break

        y_line = y + line_index * line_height
        x = x0

        if not tokens:
            continue

        for token_type, text_value in tokens:
            color = code_token_color(token_type)
            draw.text(
                (x, y_line),
                text_value,
                font=font,
                fill=color,
            )
            bbox = draw.textbbox((x, y_line), text_value, font=font)
            x = bbox[2]

    return image


def create_code_images(code, language):
    """生成一组代码 PNG，返回本地临时文件路径。"""

    code = str(code or "")
    font = get_code_font()

    # 先按真实代码行切分；图片内部再根据宽度做视觉换行。
    raw_lines = code.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    chunks = []

    for index in range(0, len(raw_lines), CODE_MAX_LINES_PER_IMAGE):
        chunks.append(raw_lines[index:index + CODE_MAX_LINES_PER_IMAGE])

    if not chunks:
        chunks = [[]]

    paths = []

    for chunk_index, chunk in enumerate(chunks, start=1):
        # 使用临时画布计算视觉行数。
        measure = Image.new("RGB", (CODE_IMAGE_WIDTH, 10), "#282C34")
        measure_draw = ImageDraw.Draw(measure)
        visual_lines = []

        for line in chunk:
            if line == "":
                visual_lines.append("")
                continue

            current = ""
            max_width = CODE_IMAGE_WIDTH - CODE_HORIZONTAL_PADDING * 2
            for char in line:
                test = current + char
                bbox = measure_draw.textbbox((0, 0), test, font=font)
                if current and (bbox[2] - bbox[0]) > max_width:
                    visual_lines.append(current)
                    current = char
                else:
                    current = test
            visual_lines.append(current)

        image_height = (
            CODE_HEADER_HEIGHT
            + CODE_VERTICAL_PADDING * 2
            + max(1, len(visual_lines)) * CODE_LINE_HEIGHT
        )

        image = Image.new(
            "RGB",
            (CODE_IMAGE_WIDTH, image_height),
            "#282C34",
        )
        draw = ImageDraw.Draw(image)

        # 顶部编辑器栏
        draw.rectangle(
            (0, 0, CODE_IMAGE_WIDTH, CODE_HEADER_HEIGHT),
            fill="#21252B",
        )
        draw.ellipse((22, 22, 36, 36), fill="#FF5F56")
        draw.ellipse((44, 22, 58, 36), fill="#FFBD2E")
        draw.ellipse((66, 22, 80, 36), fill="#27C93F")

        header_font = get_code_font(20)
        display_language = clean_code_language(language)
        draw.text(
            (CODE_IMAGE_WIDTH - 220, 17),
            display_language,
            font=header_font,
            fill="#ABB2BF",
        )

        # 直接按视觉行绘制 token。为保证宽度可控，超长行使用等宽视觉换行。
        lexer = get_code_lexer(language)
        y = CODE_HEADER_HEIGHT + CODE_VERTICAL_PADDING
        max_width = CODE_IMAGE_WIDTH - CODE_HORIZONTAL_PADDING * 2

        for original_line in chunk:
            line_parts = []
            current = ""
            for char in original_line:
                test = current + char
                bbox = draw.textbbox((0, 0), test, font=font)
                if current and (bbox[2] - bbox[0]) > max_width:
                    line_parts.append(current)
                    current = char
                else:
                    current = test
            line_parts.append(current)

            if original_line == "":
                line_parts = [""]

            for visual_line in line_parts:
                x = CODE_HORIZONTAL_PADDING
                for token_type, value in lex(visual_line, lexer):
                    color = code_token_color(token_type)
                    draw.text(
                        (x, y),
                        value,
                        font=font,
                        fill=color,
                    )
                    bbox = draw.textbbox((x, y), value, font=font)
                    x = bbox[2]
                y += CODE_LINE_HEIGHT

        fd, path = tempfile.mkstemp(
            prefix="wechat_code_",
            suffix=f"_{chunk_index}.png",
        )
        os.close(fd)

        image.save(
            path,
            format="PNG",
            optimize=True,
        )

        paths.append(path)

    return paths


def upload_article_image(access_token, image_path):
    """上传正文图片，返回微信可直接用于正文 <img src> 的 URL。"""

    url = (
        f"{WECHAT_API_BASE}"
        f"/cgi-bin/media/uploadimg"
        f"?access_token={access_token}"
    )

    boundary = "----WebKitFormBoundaryAIWechatCodeImage2026"

    with open(image_path, "rb") as f:
        file_data = f.read()

    filename = os.path.basename(image_path)

    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="media"; filename="{filename}"\r\n'
        f"Content-Type: image/png\r\n"
        f"\r\n"
    ).encode("utf-8")

    body += file_data
    body += f"\r\n--{boundary}--\r\n".encode("utf-8")

    result = http_json_request(
        url,
        method="POST",
        data=body,
        headers={
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
    )

    image_url = result.get("url", "")

    if not image_url:
        raise RuntimeError(
            "代码图片上传成功但微信没有返回正文图片 URL"
        )

    return image_url


def render_code_block(code_block, access_token):

    if not isinstance(code_block, dict):
        return ""

    code = str(code_block.get("code", "") or "")
    if not code.strip():
        return ""

    language = clean_code_language(
        code_block.get("language", "")
    )

    caption = str(
        code_block.get("caption", "") or ""
    ).strip()

    image_paths = create_code_images(code, language)
    image_urls = []

    try:
        for image_path in image_paths:
            print(
                f"上传代码图片：{os.path.basename(image_path)}"
            )
            image_url = upload_article_image(
                access_token,
                image_path,
            )
            image_urls.append(image_url)
    finally:
        for image_path in image_paths:
            try:
                os.remove(image_path)
            except OSError:
                pass

    html_parts = []

    if caption:
        caption = clean_inline_markdown(caption)
        caption = escape_text(caption)
        html_parts.append(
            f"""
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
        )

    for image_url in image_urls:
        safe_url = escape_text(image_url)
        html_parts.append(
            f"""
<p style="
    margin:14px 0 20px 0;
    padding:0;
    width:100%;
    box-sizing:border-box;
    text-align:center;
">
    <img
        src="{safe_url}"
        style="display:block;width:100%;height:auto;margin:0 auto;"
    />
</p>
""".strip()
        )

    return "\n".join(html_parts)


# ============================================================
# 顶部导语框
#
# 固定模板：
# 左上角黄色三角
# 右下角蓝色三角
# 蓝色边框
# 浅蓝背景
# ============================================================

def render_lead(lead):

    lead = str(
        lead or ""
    ).strip()

    if not lead:
        return ""

    # 清理 Markdown
    lead = clean_inline_markdown(
        lead
    )

    # HTML 转义
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

    <!-- 左上角黄色三角 -->
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

    <!-- 右下角蓝色三角 -->
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
#
# 固定模板：
#
# [蓝色折角编号标签] [浅蓝标题框] [黄色三角]
#
# 编号只在左侧标签中出现。
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

    <!-- 左侧蓝色折角编号标签 -->
    <section style="
        width:60px;
        min-width:60px;
        height:30px;
        position:relative;
        box-sizing:border-box;
        background-color:#ebf6ff;
        overflow:hidden;
    ">

        <!-- 蓝色折角主体 -->
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


    <!-- 中间标题区域 -->
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


    <!-- 右侧黄色三角 -->
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
    section,
    access_token
):

    html_parts = []

    # --------------------------------------------------------
    # 章节标题
    # --------------------------------------------------------

    html_parts.append(
        render_section_heading(
            number,
            section.get(
                "heading",
                ""
            )
        )
    )

    # --------------------------------------------------------
    # 正文段落
    # --------------------------------------------------------

    paragraphs = section.get(
        "paragraphs",
        []
    )

    for paragraph in paragraphs:

        # 清理 AI 错误输出的章节编号
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

    # --------------------------------------------------------
    # 小标题
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # 金句
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # 列表
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # 代码块
    #
    # article.json：
    #
    # "code_blocks": [
    #     {
    #         "language": "javascript",
    #         "caption": "示例代码",
    #         "code": "const app = ..."
    #     }
    # ]
    #
    # 样式统一由 Python 控制。
    # --------------------------------------------------------

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
                code_block,
                access_token
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
#
# 兼容：
#
# 1. ending 是字符串
# 2. ending 是正常段落数组
# 3. ending 被 AI 错误拆成单字数组
#
# 第 3 种情况：
#
# ["这", "篇", "文", "章"]
#
# 自动恢复成：
#
# ["这篇文章"]
#
# 防止微信公众号出现：
#
# 这
# 篇
# 文
# 章
#
# 一字一行。
# ============================================================

def normalize_ending(ending):

    # --------------------------------------------------------
    # 情况 1：
    # ending 直接是字符串
    # --------------------------------------------------------

    if isinstance(
        ending,
        str
    ):

        ending = ending.strip()

        if not ending:
            return []

        # 如果字符串内部本身有换行，
        # 按段落拆分。
        paragraphs = re.split(
            r"\n+",
            ending
        )

        return [
            paragraph.strip()
            for paragraph in paragraphs
            if paragraph.strip()
        ]

    # --------------------------------------------------------
    # 情况 2：
    # ending 不是数组
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # 去掉空内容
    # --------------------------------------------------------

    ending = [
        str(item).strip()
        for item in ending
        if str(item).strip()
    ]

    if not ending:
        return []

    # --------------------------------------------------------
    # 情况 3：
    #
    # AI 错误地把一句话拆成了单字数组：
    #
    # ["这", "篇", "文", "章", "很", "重", "要"]
    #
    # 如果数组中的每一项都是单个字符，
    # 说明它不是正常的段落数组。
    #
    # 这里把它重新拼接。
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # 正常段落数组
    # --------------------------------------------------------

    return ending


# ============================================================
# 微信公众号完整 HTML
# ============================================================

def build_wechat_html(article, access_token):

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
                section,
                access_token
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

    # --------------------------------------------------------
    # 规范化 ending
    #
    # 防止 ending 被错误拆成单字数组。
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # 来源
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # 微信图文内容
    # --------------------------------------------------------

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
#
# 只有 draft/add 成功后才记录。
# news_fetcher.py 下次运行会读取这个文件并跳过这些链接。
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
        print("警告：文章没有 original_link，无法记录已处理状态。")
        return

    links = []

    if os.path.exists(PROCESSED_NEWS_FILE):
        try:
            with open(
                PROCESSED_NEWS_FILE,
                "r",
                encoding="utf-8",
            ) as f:
                data = json.load(f)

            if isinstance(data, dict):
                links = data.get("links", [])
            elif isinstance(data, list):
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

    # 只保留最近 200 篇，避免文件无限增长。
    links = links[-MAX_PROCESSED_NEWS:]

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

    # 最后保险：
    # 防止 AI 标题残留 Markdown **
    title = re.sub(
        r"\*\*(.*?)\*\*",
        r"\1",
        title
    )

    content = build_wechat_html(
        article,
        access_token
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

    # 只有 draft/add 真正成功后，才把原文链接写入已处理记录。
    record_processed_news(article)

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
