import streamlit as st
from openai import OpenAI
from pdf2image import convert_from_bytes
import pandas as pd
import io
import json
import time
import base64

# ==========================================
# 🎨 إعدادات الصفحة
# ==========================================
st.set_page_config(page_title="مولد الأسئلة (HQ Vision)", page_icon="🦅", layout="wide")
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Tajawal:wght@400;700&display=swap');
    * {font-family: 'Tajawal', sans-serif; direction: rtl; text-align: right;}
    .debug-box {border: 2px dashed #f44336; padding: 10px; margin: 10px 0;}
</style>
""", unsafe_allow_html=True)

# ==========================================
# 🔧 دوال OpenRouter
# ==========================================

def generate_questions_openrouter(image_bytes, num_questions, api_key):
    client = OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=api_key,
    )
    
    base64_image = base64.b64encode(image_bytes).decode('utf-8')

    prompt = f"""
    أنت خبير بصري ومدرس محترف.
    1. انظر للصورة بدقة عالية (النص باللغة العربية).
    2. تجاهل أي تشويش، ركز على المحتوى النصي.
    3. استخرج {num_questions} أسئلة اختيار من متعدد.
    4. الرد يجب أن يكون JSON List فقط.
    Format: [{{"question": "...", "options": ["...", "...", "...", "..."], "answer": "..."}}]
    """

    try:
        response = client.chat.completions.create(
            model="google/gemini-flash-1.5", 
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{base64_image}"
                            },
                        },
                    ],
                }
            ],
        )
        
        content = response.choices[0].message.content
        # تنظيف الرد من علامات الكود
        json_str = content.replace('```json', '').replace('```', '').strip()
        # محاولة إصلاح الـ JSON لو فيه مشكلة
        if not json_str.startswith('['):
            start = json_str.find('[')
            end = json_str.rfind(']') + 1
            if start != -1 and end != -1:
                json_str = json_str[start:end]
                
        return json.loads(json_str)
        
    except Exception as e:
        print(f"Error parsing: {e}") # طباعة الخطأ في الكونسول
        return []

def create_excel_colored(questions_list):
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
        for col_idx, opt in enumerate(row_data[3:7]):
            if str(opt).strip() == correct:
                ws.write(excel_row, col_idx + 3, opt, green_fmt)
            else:
                ws.write(excel_row, col_idx + 3, opt, border_fmt)

    workbook.close()
    return output.getvalue()

# ==========================================
# 🖥️ الواجهة
# ==========================================
st.title("🦅 مولد الأسئلة (عالي الدقة)")
st.info("تم رفع دقة قراءة الصور (300 DPI) للتغلب على مشاكل التشفير.")

with st.sidebar:
    st.header("الإعدادات")
    # حاول تقرأ من Secrets الأول
    if 'OPENROUTER_API_KEY' in st.secrets:
        api_key = st.secrets['OPENROUTER_API_KEY']
        st.success("المفتاح تم تحميله من النظام 🔑")
    else:
        api_key = st.text_input("OpenRouter API Key", type="password")
    
    show_images = st.checkbox("عرض صور الصفحات (للتأكد)", value=True)

uploaded_file = st.file_uploader("ارفع الكتاب (PDF)", type=['pdf'])

if uploaded_file and api_key:
    col1, col2 = st.columns(2)
    with col1: start_p = st.number_input("من صفحة", 1, value=1)
    with col2: end_p = st.number_input("إلى صفحة", 1, value=2) # خليناه قليل عشان التجربة
    q_per_page = st.slider("الأسئلة لكل صفحة", 1, 10, 3)
    
    if st.button("🚀 ابدأ المعالجة"):
        progress = st.progress(0)
        status = st.empty()
        all_qs = []
        
        pdf_bytes = uploaded_file.read()
        
        # === التعديل الجوهري هنا: DPI 300 ===
        try:
            status.text("جاري تحويل الـ PDF لصور عالية الدقة...")
            images = convert_from_bytes(
                pdf_bytes, 
                first_page=start_p, 
                last_page=end_p,
                dpi=300,        # دقة عالية
                fmt='jpeg',     # صيغة خفيفة
                thread_count=2  # تسريع المعالجة
            )
            
            for i, img in enumerate(images):
                page_num = start_p + i
                status.text(f"جاري فحص صفحة {page_num}...")
                
                # عرض الصورة للمستخدم لو اختار كده
                if show_images:
                    with st.expander(f"صورة صفحة {page_num} (ما يراه الذكاء الاصطناعي)", expanded=False):
                        st.image(img, use_container_width=True)

                # تحويل الصورة
                img_byte_arr = io.BytesIO()
                img.save(img_byte_arr, format='JPEG', quality=85)
                img_bytes = img_byte_arr.getvalue()
                
                # الإرسال للذكاء الاصطناعي
                qs = generate_questions_openrouter(img_bytes, q_per_page, api_key)
                
                if qs:
                    all_qs.extend(qs)
                    st.toast(f"✅ تم استخراج {len(qs)} سؤال من صفحة {page_num}")
                else:
                    st.warning(f"⚠️ صفحة {page_num}: لم يتم استخراج أسئلة. قد تكون فارغة.")
                
                progress.progress((i+1)/len(images))
                time.sleep(1) # تفادي الحظر
                
            if all_qs:
                st.success(f"تم الانتهاء! إجمالي الأسئلة: {len(all_qs)}")
                data = create_excel_colored(all_qs)
                st.download_button("📥 تحميل ملف الأسئلة (Excel)", data, "Final_Questions.xlsx")
            else:
                st.error("لم يتم العثور على أي أسئلة في الصفحات المحددة.")
                
        except Exception as e:
            st.error(f"خطأ تقني: {e}")
