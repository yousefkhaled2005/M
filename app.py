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
st.set_page_config(page_title="مولد الأسئلة (HQ Vision)", page_icon="🦅", layout="wide")

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Tajawal:wght@400;700&display=swap');
    * {font-family: 'Tajawal', sans-serif; direction: rtl; text-align: right;}
    .stButton button {background-color: #00897B; color: white; font-size: 18px;}
    .success-box {background-color: #e0f2f1; padding: 15px; border-radius: 10px; border: 1px solid #00897B;}
</style>
""", unsafe_allow_html=True)

# ==========================================
# 🔧 دوال الذكاء الاصطناعي (Gemini Vision)
# ==========================================

def generate_questions_from_image(image_obj, num_questions, api_key):
    """إرسال صورة عالية الدقة لـ Gemini"""
    genai.configure(api_key=api_key)
    
    # نستخدم 1.5 Flash لأنه الأسرع والأذكى في قراءة الصور حالياً
    model = genai.GenerativeModel('gemini-1.5-flash') 
    
    prompt = f"""
    أنت خبير بصري ومدرس محترف.
    1. انظر للصورة المرفقة بدقة عالية (DPI 300).
    2. تجاوز أي تشويش وركز على النص العربي.
    3. استخرج {num_questions} أسئلة اختيار من متعدد (MCQ) من محتوى الصفحة.
    
    المطلوب:
    الرد JSON List فقط بدون أي مقدمات (```json ... ```).
    [
        {{"question": "نص السؤال؟", "options": ["أ", "ب", "ج", "د"], "answer": "أ"}}
    ]
    تأكد أن الإجابة موجودة حرفياً ضمن الاختيارات.
    """
    
    try:
        # Gemini بيقبل كائن الصورة (PIL Image) مباشرة
        response = model.generate_content([prompt, image_obj])
        
        # تنظيف الرد من علامات الكود (Clean Markdown)
        text = response.text
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0]
        elif "```" in text:
            text = text.split("```")[1].split("```")[0]
            
        return json.loads(text.strip())
    except Exception as e:
        print(f"Error: {e}")
        return []

def create_excel_colored(questions_list):
    """إنشاء ملف الإكسل الملون"""
    output = io.BytesIO()
    workbook = pd.ExcelWriter(output, engine='xlsxwriter')
    
    rows = []
    for q in questions_list:
        row = ["Vision AI", q['question'], ""] + q['options'] + [q['answer']]
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

st.title("🦅 مولد الأسئلة (Google Vision - HD)")
st.info("تم رفع دقة المسح الضوئي (300 DPI) لقراءة الكتب المشفرة بوضوح.")

with st.sidebar:
    st.header("الإعدادات")
    # قراءة المفتاح من Secrets لو موجود، أو من الخانة
    if 'GEMINI_API_KEY' in st.secrets:
        api_key = st.secrets['GEMINI_API_KEY']
        st.success("تم تحميل المفتاح 🔑")
    else:
        api_key = st.text_input("Gemini API Key", type="password")
    
    show_images = st.checkbox("عرض الصور (Debug Mode)", value=True)

uploaded_file = st.file_uploader("ارفع الكتاب المشفر (PDF)", type=['pdf'])

if uploaded_file and api_key:
    col1, col2 = st.columns(2)
    with col1: start_p = st.number_input("من صفحة", min_value=1, value=1)
    with col2: end_p = st.number_input("إلى صفحة", min_value=1, value=2) # عدد قليل للتجربة
    
    q_per_page = st.slider("عدد الأسئلة من كل صفحة", 1, 10, 3)
    
    if st.button("🚀 القراءة والتوليد"):
        progress_bar = st.progress(0)
        status = st.empty()
        all_questions = []
        
        pdf_bytes = uploaded_file.read()
        
        try:
            status.text("جاري تحويل الصفحات لصور عالية الدقة (HD)...")
            
            # === التعديل السحري هنا ===
            # dpi=300: بيخلي الصورة واضحة جداً
            # fmt='jpeg': عشان حجمها يكون خفيف وميخلصش الرام
            images = convert_from_bytes(
                pdf_bytes, 
                first_page=start_p, 
                last_page=end_p, 
                dpi=300, 
                fmt='jpeg'
            )
            
            total_imgs = len(images)
            for i, img in enumerate(images):
                page_num = start_p + i
                status.text(f"جاري فحص صفحة {page_num}...")
                
                # عرض الصورة للمستخدم عشان يتأكد إنها واضحة
                if show_images:
                    with st.expander(f"صورة صفحة {page_num}", expanded=False):
                        st.image(img, use_container_width=True)
                
                # إرسال الصورة لـ Gemini
                qs = generate_questions_from_image(img, q_per_page, api_key)
                
                if qs:
                    all_questions.extend(qs)
                    st.toast(f"✅ صفحة {page_num}: تم استخراج {len(qs)} سؤال")
                else:
                    st.warning(f"⚠️ صفحة {page_num}: لم يتم استخراج أسئلة (قد تكون فارغة).")
                
                progress_bar.progress((i + 1) / total_imgs)
                time.sleep(2) # راحة عشان جوجل ميزعلش
            
            if all_questions:
                st.success(f"تم الانتهاء! إجمالي الأسئلة: {len(all_questions)}")
                excel_data = create_excel_colored(all_questions)
                st.download_button(
                    "📥 تحميل بنك الأسئلة (Excel)", 
                    excel_data, 
                    "Vision_Questions_HD.xlsx", 
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
            else:
                st.error("فشلت العملية. تأكد أن الصفحات تحتوي على نص واضح.")
                
        except Exception as e:
            st.error(f"خطأ تقني: {e}")
            st.info("نصيحة: تأكد من وجود ملف packages.txt يحتوي على poppler-utils")

elif not api_key:
    st.warning("أدخل مفتاح Gemini API للبدء.")
