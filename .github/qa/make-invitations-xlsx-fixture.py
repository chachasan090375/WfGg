#!/usr/bin/env python3
import sys, zipfile
from xml.sax.saxutils import escape

out = sys.argv[1] if len(sys.argv) > 1 else '/tmp/qa-members.xlsx'
rows = [
    ('Pseudo','Rang','Code personnel'),
    ('Alpha R4','R4','111111'),
    ('Bravo R3','R3','222222'),
    ('Charlie R5','R5','333333'),
]
strings=[]
index={}
def sid(value):
    if value not in index:
        index[value]=len(strings); strings.append(value)
    return index[value]

sheet_rows=[]
for rn,row in enumerate(rows,1):
    cells=[]
    for col,value in zip(('A','B','C'),row):
        if col=='C' and rn>1:
            cells.append(f'<c r="{col}{rn}"><v>{value}</v></c>')
        else:
            cells.append(f'<c r="{col}{rn}" t="s"><v>{sid(value)}</v></c>')
    sheet_rows.append(f'<row r="{rn}">{"".join(cells)}</row>')

shared=''.join(f'<si><t>{escape(s)}</t></si>' for s in strings)
files={
'[Content_Types].xml':'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
<Override PartName="/xl/sharedStrings.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml"/>
</Types>''',
'_rels/.rels':'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>''',
'xl/workbook.xml':'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="in" sheetId="1" r:id="rId1"/></sheets></workbook>''',
'xl/_rels/workbook.xml.rels':'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/sharedStrings" Target="sharedStrings.xml"/></Relationships>''',
'xl/worksheets/sheet1.xml':f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><dimension ref="A1:C4"/><sheetData>{''.join(sheet_rows)}</sheetData></worksheet>''',
'xl/sharedStrings.xml':f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" count="{len(strings)}" uniqueCount="{len(strings)}">{shared}</sst>'''
}
with zipfile.ZipFile(out,'w',compression=zipfile.ZIP_DEFLATED) as z:
    for name,data in files.items(): z.writestr(name,data)
print(out)
