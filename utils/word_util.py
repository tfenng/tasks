import copy

import docx
from docx.enum.text import WD_TAB_ALIGNMENT
from docx.shared import Cm


class TemplateDetection:
    def __init__(self, temp_path=None):
        self.tem_path = temp_path
        self.doc = None
        self.table = None

    def head(self, title, head: list, details):
        self.doc = docx.Document(self.tem_path)
        self.table = self.doc.tables[0]
        self.table.rows[0].cells[0].text = title
        self.table.cell(0, 0).paragraphs[0].paragraph_format.alignment = WD_TAB_ALIGNMENT.CENTER
        for i, _ in enumerate(head):
            row = self.table.add_row()
            # self.table.rows[i+1]._element.addprevious(self.table.rows[1]._element)
            if len(_) == 1:
                row.cells[1].merge(row.cells[-1])
            n = 0
            for key, value in _.items():
                row.cells[n].text = key
                row.cells[n + 1].text = str(value)
                n += 2
        if details is not None:
            re = self.table.add_row()
            cells = re.cells
            cells[0].merge(cells[-1])
            re.cells[0].text = details
        row = self.table.rows[1]
        row._element.getparent().remove(row._element)

    def add_list(self, list):
        for i in range(0, len(list), 2):
            row = self.table.add_row()
            row.cells[0].text = list[i][0]
            row.cells[1].text = str(list[i][1])
            if i + 1 < len(list):
                row.cells[2].text = list[i + 1][0]
                row.cells[3].text = str(list[i + 1][1])

    def add_images(self, d, image_path_or_stream, width, height):
        for key, value in d.items():
            cells = self.table.add_row().cells
            cells[1].merge(cells[-1])
            cells[0].text = key
            cells[1].text = str(value)
        image_cells = self.table.add_row().cells
        image_cells[0].merge(image_cells[-1])
        par = image_cells[0].paragraphs[0]
        par.paragraph_format.alignment = WD_TAB_ALIGNMENT.CENTER
        par.add_run('').add_picture(image_path_or_stream, width=Cm(width), height=Cm(height))

    def save(self, path_or_stream):
        self.doc.save(path_or_stream)
