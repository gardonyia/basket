import streamlit as st
from pptx import Presentation
from pptx.util import Inches, Pt
from docx import Document
import io

# --- PPT Generáló Logika ---
def create_ppt(word_file, template_file):
    prs = Presentation(template_file)
    doc = Document(word_file)
    
    # Word tartalom kinyerése
    paragraphs = [p.text for p in doc.paragraphs if p.text.strip() != ""]

    # 1. Slide: Címoldal
    slide = prs.slides.add_slide(prs.slide_layouts[0])
    slide.shapes.title.text = "Játékosszegmentáció a Tippmixprón"
    if len(slide.placeholders) > 1:
        slide.placeholders[1].text = "Kockázatkezelés és Profitvédelem | 2025"

    # 2. Slide: Bevezetés
    slide = prs.slides.add_slide(prs.slide_layouts[1])
    slide.shapes.title.text = "A szegmentáció célkitűzései"
    tf = slide.placeholders[1].text_frame
    tf.text = "Veszélyes fogadási mintázatok azonosítása és kezelése."
    p = tf.add_paragraph()
    p.text = "Egységes limitálási rendszer a kockázatok minimalizálására."
    
    # 3. Slide: A 8 Kockázati Role
    slide = prs.slides.add_slide(prs.slide_layouts[1])
    slide.shapes.title.text = "Alkalmazott kategóriák (8 Role)"
    tf = slide.placeholders[1].text_frame
    roles = ["Bonus Abuser", "Cashout Abuser", "Monitoring", "Late Betting", 
             "Arb/Dropping", "Default", "Sport Risk", "Tipping Line"]
    for role in roles:
        p = tf.add_paragraph()
        p.text = role
        p.level = 1

    # 4. Slide: Teljesítmény adatok (Táblázat)
    slide = prs.slides.add_slide(prs.slide_layouts[5])
    slide.shapes.title.text = "Role-ok 2025-ös teljesítménye"
    
    rows, cols = 6, 4
    left, top, width, height = Inches(0.5), Inches(1.5), Inches(9), Inches(3)
    table = slide.shapes.add_table(rows, cols, left, top, width, height).table
    
    headers = ["Role", "Stakes (Ft)", "GGR (Ft)", "Margin"]
    for i, h in enumerate(headers):
        table.cell(0, i).text = h
    
    data = [
        ["Tipping Line", "16,98 Mrd", "-1,08 Mrd", "-6,40%"],
        ["Sport Risk", "4,48 Mrd", "-99,8 M", "-2,23%"],
        ["Default", "10,24 Mrd", "508,3 M", "4,96%"],
        ["Arb/Dropping", "336,3 M", "-23,4 M", "-6,97%"],
        ["Monitoring", "21,18 Mrd", "680,6 M", "3,21%"]
    ]
    
    for r_idx, row in enumerate(data):
        for c_idx, val in enumerate(row):
            table.cell(r_idx + 1, c_idx).text = val

    # 5. Slide: Megelőzött veszteségek
    slide = prs.slides.add_slide(prs.slide_layouts[1])
    slide.shapes.title.text = "Eredmények: Megelőzött veszteség"
    tf = slide.placeholders[1].text_frame
    tf.text = "Összesen: ~80,5 millió Ft megelőzött veszteség"
    for item in ["Tipping Line: -71,9 M Ft", "Sport Risk: -5,6 M Ft", "Arb/Dropping: -2,8 M Ft"]:
        p = tf.add_paragraph()
        p.text = item
        p.level = 1

    ppt_io = io.BytesIO()
    prs.save(ppt_io)
    ppt_io.seek(0)
    return ppt_io

# --- Streamlit Felület ---
st.title("🎯 Szerencsejáték Zrt. PPT Generátor")
st.write("Töltsd fel a forrásfájlokat a prezentáció összeállításához.")

up_word = st.file_uploader("Word dokumentum (Tartalom)", type="docx")
up_ppt = st.file_uploader("PPT Sablon", type="pptx")

if st.button("Prezentáció Generálása"):
    if up_word and up_ppt:
        with st.spinner("Generálás..."):
            result = create_ppt(up_word, up_ppt)
            st.success("Kész!")
            st.download_button("📥 PPTX Letöltése", result, "Segmentacio_Prezentacio.pptx")
    else:
        st.error("Mindkét fájl feltöltése szükséges!")
