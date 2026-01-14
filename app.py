import streamlit as st
import google.generativeai as genai
from pdf2image import convert_from_bytes
import pandas as pd
import io
import json
import time
from PIL import Image

# ==========================================
# 🎨 إعدادات الصفحة
# ==========================================
st.set_page_config(page_title="كاسر التشفير ومولد الأسئلة", page_icon="👁️", layout="wide")

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Tajawal:wght@400;700&display=swap');
    * {font-family: 'Tajawal', sans-serif; direction: rtl; text-align: right;}
    .stButton button {background-color: #FF5722; color: white; font-size: 18px;}
    .success-box {background-color: #e8f5e9; padding: 15px; border-radius: 10px; border: 1px solid #4CAF50;}
</style>
""", unsafe_allow_html=True)

# ==========================================
# 🔧 دوال الذكاء الاصطناعي (Vision)
# ==========================================

def generate_questions_from_image(image_obj, num_questions, api_key):
    """إرسال صورة الصفحة لـ Gemini لقراءتها وتوليد الأسئلة"""
    genai.configure(api_key=api_key)
    # نستخدم موديل 1.5 Flash لأنه سريع وبيدعم الصور
    model = genai.GenerativeModel('gemini-1.5-flash') 
    
    prompt = f"""
    أنت خبير في وضع الامتحانات.
    قم بالنظر إلى صورة صفحة الكتاب المرفقة، اقرأ النص الموجود فيها جيداً (حتى لو كان غير واضح)، ثم استخرج منه {num_questions} أسئلة اختيار من متعدد.

    المطلوب:
    الرد يجب أن يكون JSON List فقط بدون أي كلمات إضافية.
    كل عنصر يحتوي على:
    - "question": السؤال.
    - "options": قائمة 4 اختيارات.
    - "answer": الإجابة الصحيحة (يجب أن تكون واحدة من الاختيارات).
    
    Format example:
    [
        {{"question": "سؤال؟", "options": ["أ", "ب", "ج", "د"], "answer": "أ"}}
    ]
    """
    
    try:
        # هنا بنبعت الصورة + التعليمات
        response = model.generate_content([prompt, image_obj])
        json_str = response.text.replace('```json', '').replace('```', '').strip()
        return json.loads(json_str)
    except Exception as e:
        return []

def create_excel_colored(questions_list):
    """إنشاء ملف الإكسل الملون"""
    output = io.BytesIO()
    workbook = pd.ExcelWriter(output, engine='xlsxwriter')
    
    rows = []
    for q in questions_list:
        row = ["توليد بصري (Vision)", q['question'], ""] + q['options'] + [q['answer']]
        rows.append(row)
        
    df = pd.DataFrame(rows, columns=['الوحدة', 'السؤال', 'فراغ', 'Opt1', 'Opt2', 'Opt3', 'Opt4', 'RealAnswer'])
    df_to_write = df.drop(columns=['RealAnswer'])
    df_to_write.to_excel(workbook, index=False, sheet_name='بنك الأسئلة')
    
    wb = workbook.book
    ws = workbook.sheets['بنك الأسئلة']
    green_fmt = wb.add_format({'bg_color': '#00FF00', 'border': 1})
    border_fmt = wb.add_format({'border': 1})
    
    for row_idx, row_data in enumerate(rows):
        excel_row = row_idx + 1
        correct = str(row_data[-1]).strip()
        options = row_data[3:7]
        for col_idx, opt in enumerate(options):
            if str(opt).strip() == correct:
                ws.write(excel_row, col_idx + 3, opt, green_fmt)
            else:
                ws.write(excel_row, col_idx + 3, opt, border_fmt)

    workbook.close()
    return output.getvalue()

# ==========================================
# 🖥️ الواجهة
# ==========================================

st.title("👁️ مولد الأسئلة (نسخة الرؤية البصرية)")
st.info("هذه النسخة تعالج الكتب المشفرة عن طريق قراءة الصفحات كصور.")

with st.sidebar:
    st.header("الإعدادات")
    api_key = st.text_input("Gemini API Key", type="password")
    
uploaded_file = st.file_uploader("ارفع الكتاب المشفر (PDF)", type=['pdf'])

if uploaded_file and api_key:
    # تحويل الـ PDF لصور يأخذ وقت وذاكرة، لذلك نطلب تحديد صفحات قليلة
    st.warning("⚠️ بما أننا نعالج صوراً، يرجى تحديد عدد صفحات قليل في كل مرة (مثلاً 5 صفحات) لتجنب توقف السيرفر.")
    
    col1, col2 = st.columns(2)
    with col1: start_p = st.number_input("من صفحة", min_value=1, value=1)
    with col2: end_p = st.number_input("إلى صفحة", min_value=1, value=5)
    
    q_per_page = st.slider("عدد الأسئلة من كل صفحة", 1, 5, 2)
    
    if st.button("🚀 القراءة والتوليد"):
        progress_bar = st.progress(0)
        status = st.empty()
        all_questions = []
        
        # قراءة الملف كـ Bytes
        pdf_bytes = uploaded_file.read()
        
        try:
            # تحويل الصفحات المطلوبة فقط لصور
            # first_page & last_page parameters are 1-based index in pdf2image?? 
            # Actually pdf2image loads usually all, but we can splice bytes or convert specific pages.
            # الأفضل للأداء: تحويل الرينج المطلوب فقط
            
            status.text("جاري تحويل صفحات الكتاب لصور...")
            images = convert_from_bytes(pdf_bytes, first_page=start_p, last_page=end_p)
            
            total_imgs = len(images)
            for i, img in enumerate(images):
                page_num = start_p + i
                status.text(f"جاري النظر في صفحة {page_num} وتوليد الأسئلة...")
                
                # إرسال الصورة لـ Gemini
                qs = generate_questions_from_image(img, q_per_page, api_key)
                if qs:
                    all_questions.extend(qs)
                
                progress_bar.progress((i + 1) / total_imgs)
                time.sleep(1.5) # راحة للـ API
            
            if all_questions:
                st.success(f"تم استخراج {len(all_questions)} سؤال من الصور!")
                excel_data = create_excel_colored(all_questions)
                st.download_button("📥 تحميل ملف الإكسل", excel_data, "Vision_Questions.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            else:
                st.error("لم يتمكن الذكاء الاصطناعي من استخراج أسئلة. ربما الصفحة فارغة أو صورة غير واضحة.")
                
        except Exception as e:
            st.error(f"حدث خطأ أثناء معالجة الصور: {e}")
            st.warning("جرب تقليل عدد الصفحات المختارة.")

elif not api_key:
    st.warning("أدخل المفتاح أولاً.")