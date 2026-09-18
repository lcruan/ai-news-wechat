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
        r"^(?:0?[1-9]|1[0-9]|20)"
        r"\s*(?:[：:、.\-—–])?\s*",
        "",
        heading
    ).strip()

    # 如果指定了当前编号，再做一次针对性清洗
    if number is not None:

        number_text = f"{number:02d}"

        heading = re.sub(
            rf"^{re.escape(number_text)}"
            rf"\s*(?:[：:、.\-—–])?\s*",
            "",
            heading
        ).strip()

        heading = re.sub(
            rf"^{number}"
            rf"\s*(?:[：:、.\-—–])?\s*",
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
# 静态代码语法高亮
#
# 注意：
# 这里不依赖 JavaScript / highlight.js / Prism.js。
#
# Python 在生成微信公众号 HTML 时，
# 直接把代码转换成带颜色的 span。
#
# 因此微信公众号打开文章时，
# 不需要额外加载任何 JS。
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

    language_lower = str(
        language or ""
    ).strip().lower()

    # --------------------------------------------------------
    # 颜色方案
    #
    # 整体保持现代深色编辑器风格。
    # --------------------------------------------------------

    COLOR_COMMENT = "#7f848e"
    COLOR_STRING = "#98c379"
    COLOR_KEYWORD = "#c678dd"
    COLOR_NUMBER = "#d19a66"
    COLOR_FUNCTION = "#61afef"
    COLOR_TAG = "#e06c75"
    COLOR_ATTRIBUTE = "#d19a66"
    COLOR_BOOLEAN = "#56b6c2"
    COLOR_OPERATOR = "#56b6c2"
    COLOR_DEFAULT = "#abb2bf"

    # --------------------------------------------------------
    # 先进行 HTML 转义。
    #
    # 后续生成的 span 标签是我们自己添加的。
    # --------------------------------------------------------

    escaped = html.escape(
        code,
        quote=False
    )

    # --------------------------------------------------------
    # 使用占位符保护：
    #
    # 1. 注释
    # 2. 字符串
    # 3. HTML 标签
    #
    # 避免后续关键词高亮把这些内容再次处理。
    # --------------------------------------------------------

    protected = []

    def protect(value, color):

        index = len(protected)

        placeholder = (
            f"___CODE_TOKEN_{index}___"
        )

        protected.append(
            (
                placeholder,
                f'<span style="color:{color};">'
                f'{value}'
                f'</span>'
            )
        )

        return placeholder

    # --------------------------------------------------------
    # HTML / Vue 标签
    #
    # <template>
    # <div class="app">
    # </div>
    #
    # Vue 文件优先按 HTML 标签处理。
    # --------------------------------------------------------

    if language_lower in (
        "html",
        "htm",
        "xml",
        "vue"
    ):

        tag_pattern = re.compile(
            r"&lt;/?[A-Za-z][^&]*?&gt;"
        )

        def replace_tag(match):

            tag = match.group(0)

            # 标签名
            tag = re.sub(
                r"(&lt;/?)([A-Za-z][\w:-]*)",
                rf'\1<span style="color:{COLOR_TAG};">\2</span>',
                tag
            )

            # 属性名
            tag = re.sub(
                r"(\s)([A-Za-z_:][\w:.-]*)(=)",
                rf'\1<span style="color:{COLOR_ATTRIBUTE};">\2</span>\3',
                tag
            )

            return protect(
                tag,
                COLOR_DEFAULT
            )

        escaped = tag_pattern.sub(
            replace_tag,
            escaped
        )

    # --------------------------------------------------------
    # 注释
    #
    # JavaScript / TypeScript / Java / C / C++ / Go / Rust
    # Python / Bash / CSS / SQL 等常见注释。
    #
    # 注意：
    # 对 HTML/Vue，标签保护后再处理注释。
    # --------------------------------------------------------

    comment_patterns = []

    if language_lower in (
        "python",
        "py",
        "bash",
        "shell",
        "sh"
    ):
        comment_patterns.append(
            r"(?<!\\)#.*?$"
        )

    elif language_lower in (
        "sql",
    ):
        comment_patterns.extend([
            r"--.*?$",
            r"/\*[\s\S]*?\*/"
        ])

    elif language_lower in (
        "html",
        "htm",
        "xml",
        "vue"
    ):
        comment_patterns.append(
            r"&lt;!--[\s\S]*?--&gt;"
        )

    else:
        comment_patterns.extend([
            r"//.*?$",
            r"/\*[\s\S]*?\*/"
        ])

    for pattern in comment_patterns:

        escaped = re.sub(
            pattern,
            lambda m: protect(
                m.group(0),
                COLOR_COMMENT
            ),
            escaped,
            flags=re.MULTILINE
        )

    # --------------------------------------------------------
    # 字符串
    #
    # 支持：
    # "xxx"
    # 'xxx'
    # `xxx`
    #
    # 对 HTML 已经保护的标签不会再进入这里。
    # --------------------------------------------------------

    string_pattern = re.compile(
        r"""
        (?:
            "(?:\\.|[^"\\])*"
            |
            '(?:\\.|[^'\\])*'
            |
            `(?:\\.|[^`\\])*`
        )
        """,
        re.VERBOSE
    )

    escaped = string_pattern.sub(
        lambda m: protect(
            m.group(0),
            COLOR_STRING
        ),
        escaped
    )

    # --------------------------------------------------------
    # 数字
    #
    # 例如：
    # 100
    # 3.14
    # 0xff
    # --------------------------------------------------------

    escaped = re.sub(
        r"\b(?:0x[0-9a-fA-F]+|\d+(?:\.\d+)?)\b",
        lambda m: (
            f'<span style="color:{COLOR_NUMBER};">'
            f'{m.group(0)}'
            f'</span>'
        ),
        escaped
    )

    # --------------------------------------------------------
    # Boolean / null / undefined
    # --------------------------------------------------------

    escaped = re.sub(
        r"\b(?:true|false|null|undefined|None|True|False)\b",
        lambda m: (
            f'<span style="color:{COLOR_BOOLEAN};">'
            f'{m.group(0)}'
            f'</span>'
        ),
        escaped
    )

    # --------------------------------------------------------
    # 关键字
    #
    # 根据语言选择不同关键字。
    # --------------------------------------------------------

    keyword_sets = {

        "javascript": {
            "const", "let", "var",
            "function", "return",
            "if", "else", "for", "while",
            "do", "switch", "case", "break",
            "continue", "new", "class",
            "extends", "import", "from",
            "export", "default",
            "async", "await",
            "try", "catch", "finally",
            "throw", "typeof",
            "instanceof", "in", "of",
            "this", "super",
            "yield", "delete"
        },

        "typescript": {
            "const", "let", "var",
            "function", "return",
            "if", "else", "for", "while",
            "do", "switch", "case", "break",
            "continue", "new", "class",
            "extends", "implements",
            "interface", "type",
            "public", "private",
            "protected", "readonly",
            "import", "from",
            "export", "default",
            "async", "await",
            "try", "catch", "finally",
            "throw", "typeof",
            "instanceof", "in", "of",
            "this", "super",
            "as", "keyof",
            "namespace", "declare"
        },

        "jsx": {
            "const", "let", "var",
            "function", "return",
            "if", "else", "for",
            "while", "new", "class",
            "extends", "import",
            "from", "export",
            "default", "async",
            "await", "this"
        },

        "tsx": {
            "const", "let", "var",
            "function", "return",
            "if", "else", "for",
            "while", "new", "class",
            "extends", "import",
            "from", "export",
            "default", "async",
            "await", "this",
            "interface", "type",
            "implements", "public",
            "private", "readonly"
        },

        "python": {
            "def", "return",
            "if", "elif", "else",
            "for", "while", "in",
            "import", "from", "as",
            "class", "try", "except",
            "finally", "raise",
            "with", "lambda",
            "yield", "async",
            "await", "pass",
            "break", "continue",
            "global", "nonlocal",
            "is", "not", "and", "or"
        },

        "java": {
            "public", "private",
            "protected", "class",
            "interface", "extends",
            "implements", "static",
            "final", "void",
            "int", "long", "float",
            "double", "boolean",
            "char", "new",
            "return", "if", "else",
            "for", "while", "do",
            "switch", "case",
            "break", "continue",
            "try", "catch",
            "finally", "throw",
            "throws", "import",
            "package", "this",
            "super"
        },

        "c": {
            "int", "char", "float",
            "double", "void",
            "long", "short",
            "unsigned", "signed",
            "struct", "typedef",
            "const", "static",
            "extern", "return",
            "if", "else", "for",
            "while", "do",
            "switch", "case",
            "break", "continue",
            "sizeof", "include"
        },

        "cpp": {
            "int", "char", "float",
            "double", "void",
            "long", "short",
            "unsigned", "signed",
            "struct", "class",
            "public", "private",
            "protected", "template",
            "typename", "const",
            "static", "virtual",
            "override", "namespace",
            "using", "return",
            "if", "else", "for",
            "while", "do",
            "switch", "case",
            "break", "continue",
            "new", "delete",
            "nullptr", "auto"
        },

        "go": {
            "package", "import",
            "func", "return",
            "var", "const",
            "type", "struct",
            "interface", "if", "else",
            "for", "range",
            "switch", "case",
            "break", "continue",
            "go", "defer",
            "map", "chan",
            "select"
        },

        "rust": {
            "fn", "let", "mut",
            "const", "struct",
            "enum", "impl", "trait",
            "pub", "use", "mod",
            "match", "if", "else",
            "for", "while", "loop",
            "return", "self",
            "Self", "async", "await",
            "move", "ref", "where"
        },

        "php": {
            "function", "return",
            "class", "public",
            "private", "protected",
            "static", "extends",
            "implements", "new",
            "if", "else", "elseif",
            "for", "foreach",
            "while", "do",
            "switch", "case",
            "break", "continue",
            "try", "catch",
            "throw", "namespace",
            "use"
        },

        "sql": {
            "SELECT", "FROM",
            "WHERE", "INSERT",
            "INTO", "VALUES",
            "UPDATE", "SET",
            "DELETE", "CREATE",
            "TABLE", "ALTER",
            "DROP", "JOIN",
            "LEFT", "RIGHT",
            "INNER", "OUTER",
            "ON", "AS",
            "AND", "OR",
            "NOT", "NULL",
            "ORDER", "BY",
            "GROUP", "HAVING",
            "LIMIT", "OFFSET"
        },

        "bash": {
            "if", "then", "else",
            "elif", "fi", "for",
            "in", "do", "done",
            "case", "esac",
            "function", "while",
            "until", "select"
        },

        "shell": {
            "if", "then", "else",
            "elif", "fi", "for",
            "in", "do", "done",
            "case", "esac",
            "function", "while",
            "until", "select"
        }
    }

    # Vue / HTML 本身不需要普通语言关键字高亮
    # 但 Vue 中的 script 代码可能仍然会有 JS。
    keyword_set = keyword_sets.get(
        language_lower,
        set()
    )

    # JavaScript 别名
    if language_lower in (
        "js",
    ):
        keyword_set = keyword_sets["javascript"]

    if language_lower in (
        "ts",
    ):
        keyword_set = keyword_sets["typescript"]

    if language_lower in (
        "py",
    ):
        keyword_set = keyword_sets["python"]

    if language_lower in (
        "sh",
    ):
        keyword_set = keyword_sets["shell"]

    # --------------------------------------------------------
    # 关键词高亮
    # --------------------------------------------------------

    if keyword_set:

        # SQL 大小写不敏感
        if language_lower == "sql":

            keyword_pattern = (
                r"\b(?:"
                + "|".join(
                    re.escape(word)
                    for word in sorted(
                        keyword_set,
                        key=len,
                        reverse=True
                    )
                )
                + r")\b"
            )

            escaped = re.sub(
                keyword_pattern,
                lambda m: (
                    f'<span style="color:{COLOR_KEYWORD};">'
                    f'{m.group(0)}'
                    f'</span>'
                ),
                escaped,
                flags=re.IGNORECASE
            )

        else:

            keyword_pattern = (
                r"\b(?:"
                + "|".join(
                    re.escape(word)
                    for word in sorted(
                        keyword_set,
                        key=len,
                        reverse=True
                    )
                )
                + r")\b"
            )

            escaped = re.sub(
                keyword_pattern,
                lambda m: (
                    f'<span style="color:{COLOR_KEYWORD};">'
                    f'{m.group(0)}'
                    f'</span>'
                ),
                escaped
            )

    # --------------------------------------------------------
    # 函数调用
    #
    # console.log(...)
    # createApp(...)
    # fetch(...)
    #
    # 只给函数名着色，不改变代码结构。
    # --------------------------------------------------------

    escaped = re.sub(
        r"\b([A-Za-z_$][\w$]*)"
        r"(?=\s*\()",
        lambda m: (
            f'<span style="color:{COLOR_FUNCTION};">'
            f'{m.group(1)}'
            f'</span>'
        ),
        escaped
    )

    # --------------------------------------------------------
    # CSS 属性
    #
    # color: red;
    # display: flex;
    #
    # HTML 中也可能出现 style 内容，
    # 这里仅针对 CSS 语言。
    # --------------------------------------------------------

    if language_lower in (
        "css",
        "scss",
        "sass",
        "less"
    ):

        escaped = re.sub(
            r"([A-Za-z-]+)(\s*:)",
            lambda m: (
                f'<span style="color:{COLOR_FUNCTION};">'
                f'{m.group(1)}'
                f'</span>'
                f'{m.group(2)}'
            ),
            escaped
        )

    # --------------------------------------------------------
    # 操作符
    #
    # => === !== == != && || ++ --
    # --------------------------------------------------------

    escaped = re.sub(
        r"(===|!==|=>|==|!=|<=|>=|&&|\|\||\+\+|--)",
        lambda m: (
            f'<span style="color:{COLOR_OPERATOR};">'
            f'{m.group(0)}'
            f'</span>'
        ),
        escaped
    )

    # --------------------------------------------------------
    # 恢复被保护的内容
    #
    # 必须倒序恢复，避免一个 token 中包含另一个 token。
    # --------------------------------------------------------

    for placeholder, replacement in reversed(
        protected
    ):

        escaped = escaped.replace(
            placeholder,
            replacement
        )

    return escaped


# ============================================================
# 代码块
#
# 固定使用类似现代代码编辑器的深色样式：
#
# ┌─────────────────────────────┐
# │ ● ● ●       JavaScript      │
# ├─────────────────────────────┤
# │ const app = createApp(App)  │
# │ app.mount('#app')           │
# └─────────────────────────────┘
#
# 样式由 Python 固定控制。
# AI 只提供：
# language / caption / code
#
# 新增：
# 静态语法高亮。
# 不依赖微信端 JS。
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
    # 代码静态语法高亮
    #
    # 注意：
    # highlight_code() 内部会负责 HTML 转义。
    # 不要在这里再次 escape。
    # --------------------------------------------------------

    highlighted_code = highlight_code(
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
        position:relative;
    ">

        <!-- 左侧三个编辑器圆点 -->
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

        <!-- 代码语言 -->
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


    <!-- 代码主体 -->
    <section style="
        margin:0;
        padding:0;
        width:100%;
        box-sizing:border-box;
        overflow-x:auto;
        overflow-y:hidden;
    ">

        <pre style="
            margin:0;
            padding:15px 16px;
            width:100%;
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
            white-space:pre;
            word-break:normal;
            overflow-wrap:normal;
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
            white-space:pre;
        ">{highlighted_code}</code></pre>

    </section>

</section>
""".strip()


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
    section
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
