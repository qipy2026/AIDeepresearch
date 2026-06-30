"""Markdown → Word 转换: 贷后管理助手交接文档"""
import re
from docx import Document
from docx.shared import Pt, Cm, Inches, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.style import WD_STYLE_TYPE
from docx.oxml.ns import qn, nsdecls
from docx.oxml import parse_xml
import os

# ─── 样式配置 ───
FONT_BODY = "宋体"
FONT_HEADING = "黑体"
FONT_CODE = "Consolas"
FONT_QUOTE = "楷体"
SIZE_TITLE = Pt(18)
SIZE_H1 = Pt(16)
SIZE_H2 = Pt(14)
SIZE_H3 = Pt(12)
SIZE_BODY = Pt(12)
SIZE_TABLE = Pt(10.5)
SIZE_CODE = Pt(9)
LINE_SPACING = 1.5


def setup_styles(doc: Document):
    """配置文档默认样式"""
    style = doc.styles['Normal']
    font = style.font
    font.name = FONT_BODY
    font.size = SIZE_BODY
    font.color.rgb = RGBColor(0x1a, 0x1a, 0x1a)
    # 设置中文字体
    style.element.rPr.rFonts.set(qn('w:eastAsia'), FONT_BODY)
    pf = style.paragraph_format
    pf.line_spacing = LINE_SPACING
    pf.space_after = Pt(6)
    pf.space_before = Pt(0)

    # 页边距
    for section in doc.sections:
        section.top_margin = Cm(2.54)
        section.bottom_margin = Cm(2.54)
        section.left_margin = Cm(3.17)
        section.right_margin = Cm(3.17)


def add_title(doc: Document, text: str):
    """文档主标题"""
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(24)
    p.paragraph_format.space_after = Pt(24)
    run = p.add_run(text)
    run.font.name = FONT_HEADING
    run.font.size = SIZE_TITLE
    run.bold = True
    run.element.rPr.rFonts.set(qn('w:eastAsia'), FONT_HEADING)


def add_heading_styled(doc: Document, text: str, level: int):
    """带样式标题"""
    sizes = {1: SIZE_H1, 2: SIZE_H2, 3: SIZE_H3}
    pf_before = {1: Pt(24), 2: Pt(18), 3: Pt(12)}
    pf_after = {1: Pt(12), 2: Pt(8), 3: Pt(6)}

    p = doc.add_paragraph()
    p.paragraph_format.space_before = pf_before.get(level, Pt(12))
    p.paragraph_format.space_after = pf_after.get(level, Pt(6))
    p.paragraph_format.line_spacing = 1.3
    run = p.add_run(text)
    run.font.name = FONT_HEADING
    run.font.size = sizes.get(level, SIZE_H3)
    run.bold = True
    run.font.color.rgb = RGBColor(0x1a, 0x1a, 0x1a)
    run.element.rPr.rFonts.set(qn('w:eastAsia'), FONT_HEADING)


def add_body(doc: Document, text: str, bold: bool = False, indent: bool = True):
    """正文段落"""
    p = doc.add_paragraph()
    p.paragraph_format.line_spacing = LINE_SPACING
    if indent:
        p.paragraph_format.first_line_indent = Cm(0.74)  # 两个字符
    run = p.add_run(text)
    run.font.name = FONT_BODY
    run.font.size = SIZE_BODY
    run.bold = bold
    run.element.rPr.rFonts.set(qn('w:eastAsia'), FONT_BODY)


def add_quote(doc: Document, text: str):
    """引用块 (用楷体 + 缩进表示)"""
    p = doc.add_paragraph()
    p.paragraph_format.left_indent = Cm(1.5)
    p.paragraph_format.right_indent = Cm(1)
    p.paragraph_format.line_spacing = 1.3
    p.paragraph_format.space_before = Pt(4)
    p.paragraph_format.space_after = Pt(4)
    run = p.add_run(text)
    run.font.name = FONT_QUOTE
    run.font.size = Pt(10.5)
    run.italic = True
    run.font.color.rgb = RGBColor(0x55, 0x55, 0x55)
    run.element.rPr.rFonts.set(qn('w:eastAsia'), FONT_QUOTE)


def add_code_block(doc: Document, text: str):
    """代码块"""
    for line in text.strip().split('\n'):
        p = doc.add_paragraph()
        p.paragraph_format.left_indent = Cm(1)
        p.paragraph_format.line_spacing = 1.0
        p.paragraph_format.space_before = Pt(0)
        p.paragraph_format.space_after = Pt(0)
        run = p.add_run(line)
        run.font.name = FONT_CODE
        run.font.size = SIZE_CODE
        run.font.color.rgb = RGBColor(0x33, 0x33, 0x33)
        run.element.rPr.rFonts.set(qn('w:eastAsia'), FONT_BODY)


def add_bullet(doc: Document, text: str, level: int = 0):
    """项目符号列表项"""
    p = doc.add_paragraph()
    p.paragraph_format.left_indent = Cm(1.5 + level * 1.0)
    p.paragraph_format.first_line_indent = Cm(-0.5)
    p.paragraph_format.line_spacing = LINE_SPACING
    marker = "•" if level == 0 else "◦"
    run = p.add_run(f"{marker} {text}")
    run.font.name = FONT_BODY
    run.font.size = SIZE_BODY
    run.element.rPr.rFonts.set(qn('w:eastAsia'), FONT_BODY)


def add_table(doc: Document, header: list[str], rows: list[list[str]]):
    """格式化表格"""
    table = doc.add_table(rows=len(rows) + 1, cols=len(header))
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.style = 'Table Grid'

    # 表头
    for i, h in enumerate(header):
        cell = table.rows[0].cells[i]
        cell.text = ""
        p = cell.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = p.add_run(h)
        run.font.name = FONT_HEADING
        run.font.size = SIZE_TABLE
        run.bold = True
        run.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
        run.element.rPr.rFonts.set(qn('w:eastAsia'), FONT_HEADING)
        # 深蓝背景
        shading = parse_xml(f'<w:shd {nsdecls("w")} w:fill="2B579A"/>')
        cell._tc.get_or_add_tcPr().append(shading)

    # 数据行
    for r_idx, row in enumerate(rows):
        for c_idx, cell_text in enumerate(row):
            cell = table.rows[r_idx + 1].cells[c_idx]
            cell.text = ""
            p = cell.paragraphs[0]
            p.paragraph_format.line_spacing = 1.2
            run = p.add_run(cell_text)
            run.font.name = FONT_BODY
            run.font.size = SIZE_TABLE
            run.element.rPr.rFonts.set(qn('w:eastAsia'), FONT_BODY)
        # 交替行背景
        if r_idx % 2 == 1:
            for cell in table.rows[r_idx + 1].cells:
                shading = parse_xml(f'<w:shd {nsdecls("w")} w:fill="F0F4FA"/>')
                cell._tc.get_or_add_tcPr().append(shading)

    doc.add_paragraph()  # 表后空行


def add_divider(doc: Document):
    """分隔线"""
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(6)
    p.paragraph_format.space_after = Pt(6)
    run = p.add_run("─" * 50)
    run.font.size = Pt(8)
    run.font.color.rgb = RGBColor(0xCC, 0xCC, 0xCC)


def parse_markdown_text(text: str) -> list[tuple[str, str]]:
    """解析行内格式 (粗体 `**text**` → bold)"""
    parts = []
    pattern = re.compile(r'(\*\*(.+?)\*\*|`(.+?)`)')
    last = 0
    for m in pattern.finditer(text):
        if m.start() > last:
            parts.append(("normal", text[last:m.start()]))
        if m.group(2):  # **bold**
            parts.append(("bold", m.group(2)))
        elif m.group(3):  # `code`
            parts.append(("code", m.group(3)))
        last = m.end()
    if last < len(text):
        parts.append(("normal", text[last:]))
    return parts if parts else [("normal", text)]


def add_rich_paragraph(doc: Document, text: str, indent: bool = True):
    """支持行内格式的段落"""
    p = doc.add_paragraph()
    p.paragraph_format.line_spacing = LINE_SPACING
    if indent:
        p.paragraph_format.first_line_indent = Cm(0.74)
    for kind, content in parse_markdown_text(text):
        run = p.add_run(content)
        if kind == "bold":
            run.bold = True
            run.font.name = FONT_BODY
            run.font.size = SIZE_BODY
            run.element.rPr.rFonts.set(qn('w:eastAsia'), FONT_BODY)
        elif kind == "code":
            run.font.name = FONT_CODE
            run.font.size = Pt(10)
            run.element.rPr.rFonts.set(qn('w:eastAsia'), FONT_BODY)
        else:
            run.font.name = FONT_BODY
            run.font.size = SIZE_BODY
            run.element.rPr.rFonts.set(qn('w:eastAsia'), FONT_BODY)


def _parse_lines_to_doc(doc: Document, lines: list[str]):
    """将 markdown 行列表解析到 docx Document 对象中。"""
    i = 0
    in_code_block = False
    in_table = False
    code_lines = []
    table_header = []
    table_rows = []

    while i < len(lines):
        line = lines[i].rstrip()

        # 代码块
        if line.startswith("```"):
            if in_code_block:
                add_code_block(doc, "\n".join(code_lines))
                code_lines = []
                in_code_block = False
            else:
                in_code_block = True
            i += 1
            continue

        if in_code_block:
            code_lines.append(line)
            i += 1
            continue

        # 空行
        if not line:
            i += 1
            continue

        # 分隔线
        if line.strip() == "---":
            add_divider(doc)
            i += 1
            continue

        # 表格
        if line.startswith("|") and line.endswith("|"):
            cells = [c.strip() for c in line.split("|")[1:-1]]
            if all(c.startswith("---") or c.startswith(":--") for c in cells):
                i += 1  # 跳过分隔行
                continue
            if not in_table:
                table_header = cells
                in_table = True
            else:
                table_rows.append(cells)

            # 检测表格结束
            if i + 1 >= len(lines) or not lines[i + 1].strip().startswith("|"):
                if table_header:
                    add_table(doc, table_header, table_rows)
                table_header = []
                table_rows = []
                in_table = False
            i += 1
            continue

        # 标题
        for level in range(3, 0, -1):
            prefix = "#" * level + " "
            if line.startswith(prefix):
                text = line[len(prefix):].strip()
                add_heading_styled(doc, text, level)
                break
        else:
            # 引用
            if line.startswith("> "):
                text = line[2:].strip()
                # 去掉行内 markdown 标记
                text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
                text = re.sub(r'`(.+?)`', r'\1', text)
                add_quote(doc, text)
            # 项目符号
            elif line.startswith("- ") or line.startswith("* "):
                text = re.sub(r'\*\*(.+?)\*\*', r'\1', line[2:].strip())
                text = re.sub(r'`(.+?)`', r'\1', text)
                add_bullet(doc, text)
            # 编号列表
            elif re.match(r'^\d+\.\s', line):
                text = re.sub(r'\*\*(.+?)\*\*', r'\1', re.sub(r'^\d+\.\s', '', line).strip())
                text = re.sub(r'`(.+?)`', r'\1', text)
                add_bullet(doc, text)
            # 普通段落
            else:
                text = re.sub(r'`(.+?)`', r'\1', line)
                add_rich_paragraph(doc, text)

        i += 1


def convert_md_to_docx_bytes(md_path: str):
    """将 Markdown 文件转换为 Word 文档，返回内存 BytesIO。

    复用 setup_styles 和 _parse_lines_to_doc 的样式与解析逻辑。
    调用方负责在合适时机关闭返回的 BytesIO。
    """
    from io import BytesIO

    doc = Document()
    setup_styles(doc)

    with open(md_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    _parse_lines_to_doc(doc, lines)

    buf = BytesIO()
    doc.save(buf)
    buf.seek(0)
    return buf


def convert_md_to_docx(md_path: str, docx_path: str):
    """主转换函数（磁盘到磁盘）。"""
    buf = convert_md_to_docx_bytes(md_path)
    with open(docx_path, 'wb') as f:
        f.write(buf.read())
    buf.close()
    print(f"[OK] {docx_path}")


if __name__ == "__main__":
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    docs_dir = os.path.join(base, "docs")

    files = [
        ("交接-产品总览与功能模块.md", "交接-产品总览与功能模块.docx"),
        ("交接-数据源矩阵.md", "交接-数据源矩阵.docx"),
    ]

    for md_name, docx_name in files:
        md_path = os.path.join(docs_dir, md_name)
        docx_path = os.path.join(docs_dir, docx_name)
        if os.path.exists(md_path):
            convert_md_to_docx(md_path, docx_path)
        else:
            print(f"[SKIP] 文件不存在: {md_path}")

    print("")

    print("Conversion complete!")
