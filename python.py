import streamlit as st
import pandas as pd
import numpy as np
import numpy_financial as npf # Thư viện chuẩn cho các hàm tài chính (NPV, IRR)
import json
from google import genai
from google.genai.errors import APIError

# --- Cấu hình Trang Streamlit ---
st.set_page_config(
    page_title="App Đánh Giá Dự Án Kinh Doanh (AI-Powered)",
    layout="wide"
)

st.title("Ứng dụng Đánh giá Dự án Kinh doanh 💰")
st.markdown("Sử dụng AI để trích xuất dữ liệu, tính toán dòng tiền và đánh giá hiệu quả đầu tư (NPV, IRR, PP, DPP).")

# --- UI Sidebar: Cấu hình và API Key ---
with st.sidebar:
    st.header("Cấu hình API & Dữ liệu")
    # Lấy API Key từ Streamlit Secrets hoặc input của người dùng
    api_key = st.text_input("Nhập Khóa API Gemini:", type="password", help="Vui lòng nhập khóa API của bạn.")
    
    if api_key and not api_key.startswith('sk-'):
        st.warning("Định dạng Khóa API có vẻ không đúng.")
    
    # Định nghĩa cấu trúc JSON mong muốn cho AI
    JSON_SCHEMA = {
        "type": "object",
        "properties": {
            "Vốn đầu tư (VND)": {"type": "number", "description": "Tổng vốn đầu tư ban đầu của dự án."},
            "Dòng đời dự án (năm)": {"type": "integer", "description": "Số năm hoạt động của dự án."},
            "Doanh thu hàng năm (VND)": {"type": "number", "description": "Tổng doanh thu ước tính hàng năm."},
            "Chi phí hoạt động hàng năm (VND)": {"type": "number", "description": "Tổng chi phí hoạt động ước tính hàng năm (chưa bao gồm thuế, khấu hao)."},
            "WACC (chiết khấu)": {"type": "number", "description": "Tỷ lệ chi phí vốn bình quân (dạng thập phân, ví dụ: 0.10 cho 10%)."},
            "Thuế suất": {"type": "number", "description": "Thuế suất thu nhập doanh nghiệp (dạng thập phân, ví dụ: 0.20 cho 20%)."}
        },
        "required": [
            "Vốn đầu tư (VND)", "Dòng đời dự án (năm)", 
            "Doanh thu hàng năm (VND)", "Chi phí hoạt động hàng năm (VND)", 
            "WACC (chiết khấu)", "Thuế suất"
        ]
    }
    
    # Textarea để người dùng dán nội dung từ file Word
    project_text = st.text_area(
        "1. Dán nội dung dự án kinh doanh (từ file Word) vào đây:", 
        height=300,
        placeholder="Vui lòng dán toàn bộ nội dung tài liệu dự án vào đây để AI trích xuất dữ liệu."
    )
    
    st.info("Để đảm bảo độ tin cậy, ứng dụng yêu cầu bạn dán nội dung văn bản từ file Word.")


# --- Hàm gọi AI để trích xuất dữ liệu (Chức năng 1) ---
@st.cache_data(show_spinner=False)
def extract_financial_data(text_input, api_key):
    """Sử dụng Gemini để trích xuất các tham số tài chính cốt lõi và trả về dạng JSON."""
    if not api_key:
        st.error("Lỗi: Vui lòng cung cấp Khóa API Gemini.")
        return None
        
    try:
        client = genai.Client(api_key=api_key)
        
        prompt = f"""
        Bạn là một chuyên gia phân tích dữ liệu. Nhiệm vụ của bạn là trích xuất 6 tham số tài chính cốt lõi sau từ văn bản dự án được cung cấp.
        
        Văn bản đầu vào:
        ---
        {text_input}
        ---
        
        Vui lòng đảm bảo các giá trị:
        - Là số, không có ký hiệu tiền tệ (VND, $...).
        - WACC và Thuế suất phải là số thập phân (ví dụ: 10% là 0.10).
        - Trả về kết quả CHỈ dưới dạng JSON tuân thủ cấu trúc đã cho. Nếu không tìm thấy, hãy cố gắng ước lượng hợp lý hoặc ghi nhận 0 nếu không thể ước lượng.
        """
        
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
            config={"response_mime_type": "application/json", "response_schema": JSON_SCHEMA}
        )
        
        # Xử lý chuỗi JSON đầu ra (đôi khi AI có thể thêm ký tự thừa)
        json_text = response.text.strip()
        data = json.loads(json_text)
        return data

    except APIError as e:
        st.error(f"Lỗi gọi Gemini API: Vui lòng kiểm tra Khóa API hoặc giới hạn sử dụng. Chi tiết lỗi: {e}")
        return None
    except json.JSONDecodeError:
        st.error("Lỗi: AI trả về định dạng JSON không hợp lệ. Vui lòng thử lại với nội dung dự án rõ ràng hơn.")
        return None
    except Exception as e:
        st.error(f"Đã xảy ra lỗi không xác định trong quá trình trích xuất: {e}")
        return None

# --- Hàm tính toán các chỉ số (Chức năng 3) ---
def calculate_project_metrics(df_cashflow, WACC, investment):
    """Tính toán NPV, IRR, PP và DPP."""
    
    cashflows = df_cashflow['Dòng tiền ròng (NCF)'].tolist()
    
    # 1. NPV và IRR
    try:
        npv_value = npf.npv(WACC, cashflows)
        # npf.irr yêu cầu dòng tiền bắt đầu bằng khoản đầu tư âm (index 0)
        irr_value = npf.irr(cashflows)
    except Exception:
        # Xử lý trường hợp IRR không thể tính toán (ví dụ: dòng tiền chỉ có lỗ)
        npv_value = np.nan
        irr_value = np.nan
        
    # 2. PP (Payback Period) - Thời gian hoàn vốn
    cumulative_cf = np.cumsum(cashflows)
    payback_period = np.nan
    for i in range(1, len(cumulative_cf)):
        if cumulative_cf[i] >= 0:
            # Năm cuối cùng trước khi hoàn vốn (có dòng tiền âm)
            year_before = i - 1
            # Khoản chưa hoàn vốn vào cuối năm trước
            unrecovered_amount = -cumulative_cf[year_before]
            # NCF của năm hoàn vốn
            cf_of_payback_year = cashflows[i]
            # Tính thời gian hoàn vốn
            payback_period = year_before + (unrecovered_amount / cf_of_payback_year)
            break

    # 3. DPP (Discounted Payback Period) - Thời gian hoàn vốn có chiết khấu
    discounted_cf = [cf / ((1 + WACC) ** t) for t, cf in enumerate(cashflows)]
    cumulative_dcf = np.cumsum(discounted_cf)
    discounted_payback_period = np.nan
    for i in range(1, len(cumulative_dcf)):
        if cumulative_dcf[i] >= 0:
            year_before = i - 1
            unrecovered_amount = -cumulative_dcf[year_before]
            dcf_of_payback_year = discounted_cf[i]
            discounted_payback_period = year_before + (unrecovered_amount / dcf_of_payback_year)
            break
            
    return {
        "NPV": npv_value,
        "IRR": irr_value,
        "PP": payback_period,
        "DPP": discounted_payback_period
    }

# --- Hàm gọi AI để phân tích chỉ số (Chức năng 4) ---
@st.cache_data(show_spinner=False)
def get_ai_analysis(metrics_data, WACC, api_key):
    """Gửi các chỉ số và WACC cho Gemini để phân tích."""
    if not api_key:
        return "Lỗi: Vui lòng cung cấp Khóa API Gemini."
        
    try:
        client = genai.Client(api_key=api_key)
        
        prompt = f"""
        Bạn là một chuyên gia phân tích đầu tư và ra quyết định. Hãy phân tích các chỉ số hiệu quả dự án sau:
        
        - NPV (Giá trị hiện tại ròng): {metrics_data['NPV']:,.0f} VND
        - IRR (Tỷ suất sinh lời nội tại): {metrics_data['IRR'] * 100:.2f}%
        - WACC (Tỷ lệ chiết khấu): {WACC * 100:.2f}%
        - PP (Thời gian hoàn vốn): {metrics_data['PP']:.2f} năm
        - DPP (Thời gian hoàn vốn chiết khấu): {metrics_data['DPP']:.2f} năm
        
        Dựa trên dữ liệu trên:
        1. Đưa ra Quyết định đầu tư (Chấp nhận/Từ chối) và giải thích dựa trên NPV và IRR so với WACC.
        2. Đánh giá tính thanh khoản của dự án (thời gian thu hồi vốn).
        3. Đưa ra nhận xét tổng thể, tập trung vào rủi ro và khuyến nghị.
        
        Hãy viết bài phân tích chuyên nghiệp, súc tích (khoảng 4-5 đoạn).
        """
        
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt
        )
        return response.text

    except APIError as e:
        return f"Lỗi gọi Gemini API: Vui lòng kiểm tra Khóa API. Chi tiết lỗi: {e}"
    except Exception as e:
        return f"Đã xảy ra lỗi không xác định trong quá trình phân tích: {e}"


# --- Logic Chính của Ứng dụng ---
if st.sidebar.button("▶️ 1. Lọc dữ liệu và Xây dựng Dòng tiền"):
    if not api_key or not project_text:
        st.error("Vui lòng nhập Khóa API và dán nội dung dự án kinh doanh.")
    else:
        st.session_state['ai_data'] = None
        st.session_state['metrics'] = None
        
        with st.spinner('Đang gửi văn bản dự án cho AI để trích xuất dữ liệu cốt lõi...'):
            extracted_data = extract_financial_data(project_text, api_key)
            
        if extracted_data:
            st.session_state['ai_data'] = extracted_data
            
            V0 = extracted_data.get("Vốn đầu tư (VND)", 0)
            N = extracted_data.get("Dòng đời dự án (năm)", 0)
            R = extracted_data.get("Doanh thu hàng năm (VND)", 0)
            C = extracted_data.get("Chi phí hoạt động hàng năm (VND)", 0)
            T = extracted_data.get("Thuế suất", 0.2)
            
            # --- Chức năng 2: Xây dựng Bảng Dòng tiền ---
            st.subheader("2. Bảng Dòng tiền Ròng (Net Cash Flow - NCF)")
            
            # Giả định: Thuế suất áp dụng cho Lợi nhuận trước thuế (R - C)
            # Khấu hao = 0 để đơn giản, NCF = Lợi nhuận sau thuế + Khấu hao (tức là Lợi nhuận sau thuế)
            NCF_annual = (R - C) * (1 - T)
            
            if N <= 0:
                 st.error("Lỗi: Dòng đời dự án phải lớn hơn 0.")
            else:
                years = list(range(N + 1))
                data = {
                    'Năm': years,
                    'Doanh thu': [0] + [R] * N,
                    'Chi phí': [0] + [C] * N,
                    'Lợi nhuận trước thuế (EBT)': [0] + [R - C] * N,
                    'Thuế (T)': [0] + [(R - C) * T] * N,
                    'Dòng tiền ròng (NCF)': [-V0] + [NCF_annual] * N
                }
                df_cashflow = pd.DataFrame(data)
                
                # Định dạng hiển thị
                df_cashflow_display = df_cashflow.copy()
                for col in ['Doanh thu', 'Chi phí', 'Lợi nhuận trước thuế (EBT)', 'Thuế (T)', 'Dòng tiền ròng (NCF)']:
                    df_cashflow_display[col] = df_cashflow_display[col].apply(lambda x: f"{x:,.0f}" if x is not None else 'N/A')
                
                st.dataframe(df_cashflow_display, hide_index=True, use_container_width=True)
                
                st.session_state['df_cashflow'] = df_cashflow
                st.session_state['financial_params'] = extracted_data
                st.success("Trích xuất dữ liệu và xây dựng bảng dòng tiền thành công!")


# --- Giai đoạn 3: Tính toán và Phân tích ---
if 'df_cashflow' in st.session_state:
    
    WACC = st.session_state['financial_params'].get("WACC (chiết khấu)", 0)
    V0 = st.session_state['financial_params'].get("Vốn đầu tư (VND)", 0)
    
    st.subheader("3. Các Chỉ số Đánh giá Hiệu quả Dự án")
    
    # Tính toán các chỉ số
    metrics = calculate_project_metrics(st.session_state['df_cashflow'], WACC, V0)
    st.session_state['metrics'] = metrics
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric(
            label="NPV (Giá trị hiện tại ròng)", 
            value=f"{metrics['NPV']:,.0f} VND" if not np.isnan(metrics['NPV']) else "Không xác định"
        )
    with col2:
        st.metric(
            label="IRR (Tỷ suất sinh lời nội tại)", 
            value=f"{metrics['IRR'] * 100:.2f} %" if not np.isnan(metrics['IRR']) else "Không xác định"
        )
    with col3:
        st.metric(
            label="PP (Thời gian hoàn vốn)", 
            value=f"{metrics['PP']:.2f} năm" if not np.isnan(metrics['PP']) else "Không hoàn vốn"
        )
    with col4:
        st.metric(
            label="DPP (Thời gian hoàn vốn CK)", 
            value=f"{metrics['DPP']:.2f} năm" if not np.isnan(metrics['DPP']) else "Không hoàn vốn"
        )
        
    st.write(f"**WACC (Chi phí vốn):** {WACC * 100:.2f} %")
    st.write(f"**Vốn đầu tư ban đầu (V0):** {V0:,.0f} VND")
    

    # --- Chức năng 4: Phân tích AI ---
    st.subheader("4. Phân tích Chuyên sâu về Hiệu quả Dự án (AI)")
    
    if st.button("▶️ Yêu cầu AI Phân tích Hiệu quả", type="primary"):
        if 'metrics' in st.session_state and not np.isnan(st.session_state['metrics']['NPV']):
            with st.spinner('Đang gửi chỉ số và chờ Gemini AI đánh giá...'):
                ai_result = get_ai_analysis(st.session_state['metrics'], WACC, api_key)
                st.markdown("**Kết quả Phân tích từ Gemini AI:**")
                st.info(ai_result)
        else:
            st.warning("Vui lòng thực hiện bước 'Lọc dữ liệu và Xây dựng Dòng tiền' trước.")
            
# --- Tình trạng ban đầu ---
if 'df_cashflow' not in st.session_state:
    st.info("Bắt đầu bằng cách nhập Khóa API và dán nội dung dự án kinh doanh vào sidebar, sau đó nhấn nút **'Lọc dữ liệu và Xây dựng Dòng tiền'**.")
