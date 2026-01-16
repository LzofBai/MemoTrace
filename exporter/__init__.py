# 暂时注释掉DocxExporter的导入，直到用户安装了python-docx库
from exporter.exporter_txt import TxtExporter
from exporter.exporter_ai_txt import AiTxtExporter
from exporter.exporter_csv import CSVExporter
from exporter.exporter_html import HtmlExporter
# from exporter.exporter_docx import DocxExporter  # 注释掉，需要时单独导入
from exporter.exporter_markdown import MarkdownExporter
from exporter.exporter_xlsx import ExcelExporter