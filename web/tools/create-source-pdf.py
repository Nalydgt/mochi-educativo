"""Original digital teaching handout used to verify extraction page references."""
from pathlib import Path
from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
import pymupdf
root=Path(__file__).resolve().parents[1]
out=root/'output/pdf';out.mkdir(parents=True,exist_ok=True)
styles=getSampleStyleSheet()
styles['Title'].fontName='Helvetica-Bold';styles['Title'].textColor=colors.HexColor('#174F72')
styles['Title'].alignment=TA_LEFT;styles['Title'].fontSize=24;styles['Title'].leading=29
styles['BodyText'].fontName='Helvetica';styles['BodyText'].fontSize=11;styles['BodyText'].leading=16;styles['BodyText'].spaceAfter=12
paragraphs=(root/'fixtures/vertebrados.txt').read_text(encoding='utf-8').split('\n\n')
story=[Paragraph('PELUQO / CUADERNO DE EXPLORACION',styles['Heading3']),Paragraph(paragraphs[0],styles['Title']),Spacer(1,15)]
story.extend(Paragraph(p.replace('\n',' '),styles['BodyText']) for p in paragraphs[1:])
def footer(c,doc):
 c.setFont('Helvetica',9);c.setFillColor(colors.HexColor('#596A76'));c.drawString(48,30,'Material original del piloto - Primaria, 9 a 12 años');c.drawRightString(547,30,str(doc.page))
target=out/'expedicion-vertebrados.pdf'
SimpleDocTemplate(str(target),pagesize=(595,842),leftMargin=48,rightMargin=48,topMargin=46,bottomMargin=52).build(story,onFirstPage=footer,onLaterPages=footer)
pdf=pymupdf.open(target)
assert all(page.get_text().strip() for page in pdf)
for i,page in enumerate(pdf):page.get_pixmap(matrix=pymupdf.Matrix(1.3,1.3)).save(out/f'vertebrados-page-{i+1}.png')
print({'pdf':str(target),'pages':len(pdf)})
