"""基于 Pygments 的代码高亮。

提供：
1. 一个轻量级 ARM（A32/A64/Cortex-M）汇编 lexer，Pygments 原生不支持。
2. 一个 Markdown Preprocessor，直接对围栏代码块调用 Pygments 高亮，
   从而绕开 python-markdown 内置 codehilite 对自定义 lexer 的限制。
"""

from __future__ import annotations

import re

from markdown.preprocessors import Preprocessor
from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexer import RegexLexer
from pygments.lexers import get_lexer_by_name
from pygments.token import Comment, Keyword, Name, Number, Punctuation, String, Text, Whitespace
from pygments.util import ClassNotFound


class ArmLexer(RegexLexer):
    """Best-effort ARM 汇编 lexer。

    覆盖常见指令、寄存器、汇编器指令、注释、数字与字符串。
    未识别的符号会回退为普通文本，不会导致构建失败。
    """

    name = "ARM Assembly"
    aliases = ["arm", "armasm", "aarch64", "thumb"]
    filenames = ["*.s", "*.S", "*.asm"]

    directives = (
        r"\.(?:syntax|section|text|data|bss|rodata|global|globl|local|weak|extern|"
        r"type|size|align|balign|p2align|arm|thumb_func|thumb|code\s*16|cpu|fpu|"
        r"arch|eabi_attribute|word|hword|short|byte|ascii|asciz|string|space|skip|"
        r"zero|fill|equiv|equ|set|macro|endm|altmacro|noaltmacro|ifdef|ifndef|"
        r"endif|else|if|include|incbin|rept|endr|ltorg|pool|org|module|fnstart|"
        r"fnend|personality|handlerdata|save|movsp|pad|end)"
    )
    mnemonics = (
        r"(?:adc|adcs|add|adds|adr|adrl|and|ands|asr|asrs|b|bl|bx|blx|bic|bics|"
        r"bkpt|b\w\w|cbz|cbnz|clrex|clz|cmp|cmn|cps|cpsid|cpsie|dbg|dmb|dsb|"
        r"eor|eors|isb|ittt|itee|itt|ite|it|ldmia|ldmdb|ldmfd|ldmed|ldmib|ldmda|"
        r"ldm|ldrsb|ldrsh|ldrexb|ldrexh|ldrb|ldrh|ldrd|ldrex|ldr|lsl|lsls|lsr|"
        r"lsrs|mla|mls|movs|movw|movt|mov|mrc|mcr|mrs|msr|mul|muls|mvn|mvns|nop|"
        r"orr|orrs|pop|push|qadd|qsub|rev16|revsh|rev|ror|rors|rsb|rsbs|rsc|sbc|"
        r"sbcs|sdiv|smlal|smull|stmia|stmdb|stmfd|stmed|stmib|stmda|stm|strb|"
        r"strh|strd|strex|str|sub|subs|svc|swi|sxtb|sxth|teq|tst|udiv|umlal|"
        r"umull|uxtb|uxth|wfe|wfi|yield)"
    )
    registers = (
        r"(?:r(?:1[0-5]|[0-9])|sp|lr|pc|a[1-4]|v[1-8]|sb|sl|fp|ip|cpsr|spsr|"
        r"x(?:[12]?[0-9]|30)|w(?:[12]?[0-9]|30)|xzr|wzr|"
        r"s(?:[12]?[0-9]|3[01])|d(?:[12]?[0-9]|3[01])|q(?:[0-9]|1[0-5])|"
        r"v(?:[12]?[0-9]|3[01])|c(?:[0-9]|1[0-5])|p(?:[0-9]|1[0-5])|"
        r"fpscr|fpexc|primask|basepri|faultmask|control)"
    )

    tokens = {
        "root": [
            (r"@[^\n]*", Comment.Single),
            (r"//[^\n]*", Comment.Single),
            (r"/\*", Comment.Multiline, "comment"),
            (directives, Keyword.Declaration),
            (r"\b" + mnemonics + r"\b(?![:.\w])", Keyword),
            (r"\b" + registers + r"\b", Name.Builtin),
            (r"#[0-9a-fA-F_xX]+", Number.Hex),
            (r"\b0[xX][0-9a-fA-F_]+\b", Number.Hex),
            (r"\b0[bB][01_]+\b", Number.Bin),
            (r"\b\d[\d_]*\b", Number.Integer),
            (r'"(?:[^"\\]|\\.)*"', String.Double),
            (r"'(?:[^'\\]|\\.)*'", String.Char),
            (r"\b[A-Za-z_.$][\w.$]*:", Name.Label),
            (r"\b[A-Za-z_][\w.]*\b", Name),
            (r"[{}[\]();,+#\-=!]", Punctuation),
            (r"\s+", Whitespace),
            (r".", Text),
        ],
        "comment": [
            (r"[^*/]+", Comment.Multiline),
            (r"/\*", Comment.Multiline, "#push"),
            (r"\*/", Comment.Multiline, "#pop"),
            (r"[*/]", Comment.Multiline),
        ],
    }


FENCED_BLOCK_RE = re.compile(
    r"^(?P<fence>`{3,}|~{3,})[ \t]*(?P<lang>[\w#.+-]*)[ \t]*\n"
    r"(?P<code>.*?)(?<=\n)^(?P=fence)[ \t]*$",
    re.MULTILINE | re.DOTALL,
)


def resolve_lexer(lang: str):
    """把围栏语言名解析为 Pygments lexer，未知语言回退为纯文本。"""
    lang = (lang or "").strip().lower()
    if lang in ("arm", "armasm", "aarch64", "thumb"):
        return ArmLexer()

    aliases = {
        "sh": "bash",
        "shell": "bash",
        "makefile": "make",
        "c++": "cpp",
    }
    lang = aliases.get(lang, lang)
    if not lang:
        return get_lexer_by_name("text")
    try:
        return get_lexer_by_name(lang)
    except ClassNotFound:
        return get_lexer_by_name("text")


def highlight_code(code: str, lang: str) -> str:
    code = code.rstrip("\n")
    lexer = resolve_lexer(lang)
    formatter = HtmlFormatter(cssclass="highlight", wrapcode=True, nowrap=False)
    return highlight(code, lexer, formatter)


class HighlightCodePreprocessor(Preprocessor):
    """在 Markdown 解析前提取围栏代码块并调用 Pygments 高亮。"""

    def run(self, lines):
        text = "\n".join(lines)
        pos = 0
        out = []
        for match in FENCED_BLOCK_RE.finditer(text):
            out.append(text[pos:match.start()])
            lang = match.group("lang") or ""
            html = highlight_code(match.group("code"), lang)
            placeholder = self.md.htmlStash.store(html)
            out.append("\n" + placeholder + "\n")
            pos = match.end()
        out.append(text[pos:])
        return "".join(out).split("\n")
