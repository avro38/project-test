from pathlib import Path
import pdfplumber
from PIL import Image,ImageOps,ImageDraw
b=Path(r'G:/My Drive/U/invest strart 2.0/01_Портфель_0104')
with pdfplumber.open(b/'Итоги_первого_года_0104_2026-10-15.pdf') as d:
 sheet=Image.new('RGB',(1050,1515),'#aaaaaa')
 for i,p in enumerate(d.pages):
  im=p.to_image(resolution=85).original
  im.save(b/f'Анализ/page_{i+1}.png')
  im.thumbnail((340,480))
  sheet.paste(im,((i%3)*350,(i//3)*505))
 sheet.save(b/'Анализ/preview.png')
