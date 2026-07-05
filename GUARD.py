import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
from google.oauth2.credentials import Credentials as UserCredentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaInMemoryUpload
from datetime import datetime, date
from io import BytesIO
from PIL import Image
import time

# --- 頁面設定（手機友善）---
st.set_page_config(
    page_title="漢平世家收款系統",
    layout="centered",
    page_icon="🏢",
    initial_sidebar_state="collapsed"
)

# --- 手機友善 CSS ---
st.markdown("""
<style>
    .stButton > button { font-size: 1.2rem; padding: 0.6rem 1rem; }
    .stSelectbox label, .stDateInput label, .stNumberInput label,
    .stTextArea label, .stMultiSelect label { font-size: 1.1rem; }
    section[data-testid="stSidebar"] { display: none; }
    .block-container { padding-top: 1rem; max-width: 600px; }
</style>
""", unsafe_allow_html=True)

# --- Google 連線設定 ---
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]
SPREADSHEET_NAME = "漢平世家收款系統"


@st.cache_resource(ttl=300)
def get_credentials():
    """取得 Google 認證"""
    return Credentials.from_service_account_info(
        st.secrets["gcp_service_account"], scopes=SCOPES
    )


@st.cache_resource(ttl=300)
def get_gsheet_client():
    """取得 Google Sheets 客戶端"""
    creds = get_credentials()
    return gspread.authorize(creds)


def get_spreadsheet():
    """取得試算表"""
    client = get_gsheet_client()
    return client.open(SPREADSHEET_NAME)


def get_drive_service():
    """用 Billy 的 OAuth 憑證建立 Drive 服務（使用 30TB 空間）"""
    oauth = st.secrets["google_drive_oauth"]
    creds = UserCredentials(
        token=None,
        refresh_token=oauth["refresh_token"],
        client_id=oauth["client_id"],
        client_secret=oauth["client_secret"],
        token_uri="https://oauth2.googleapis.com/token"
    )
    return build('drive', 'v3', credentials=creds)


def get_drive_folder_id():
    """取得照片資料夾 ID"""
    service = get_drive_service()
    results = service.files().list(
        q="name='漢平世家照片' and mimeType='application/vnd.google-apps.folder' and trashed=false",
        fields="files(id)"
    ).execute()
    files = results.get('files', [])
    return files[0]['id'] if files else None


def upload_photo_to_drive(photo_bytes, filename):
    """上傳照片到 Google Drive（使用 Billy 的 30TB 空間）"""
    service = get_drive_service()
    folder_id = get_drive_folder_id()
    if not folder_id:
        return ""
    file_metadata = {'name': filename, 'parents': [folder_id]}
    media = MediaInMemoryUpload(photo_bytes, mimetype='image/jpeg')
    file = service.files().create(
        body=file_metadata, media_body=media, fields='id,webViewLink'
    ).execute()
    # 設為公開可檢視
    service.permissions().create(
        fileId=file['id'],
        body={'type': 'anyone', 'role': 'reader'}
    ).execute()
    return file.get('webViewLink', '')


def compress_image(image_bytes, max_size=800):
    """壓縮照片"""
    img = Image.open(BytesIO(image_bytes))
    img.thumbnail((max_size, max_size))
    if img.mode == 'RGBA':
        img = img.convert('RGB')
    output = BytesIO()
    img.save(output, format='JPEG', quality=75)
    return output.getvalue()


def get_residents():
    """從 Google Sheet 讀取住戶清單"""
    try:
        ss = get_spreadsheet()
        ws = ss.worksheet("住戶清單")
        records = ws.get_all_records()
        return records
    except Exception as e:
        st.error(f"讀取住戶清單失敗：{e}")
        return []


def get_records(sheet_name):
    """讀取指定工作表的所有紀錄"""
    try:
        ss = get_spreadsheet()
        ws = ss.worksheet(sheet_name)
        records = ws.get_all_records()
        return records
    except Exception as e:
        st.error(f"讀取 {sheet_name} 失敗：{e}")
        return []


def append_record(sheet_name, row_data):
    """新增一筆紀錄到指定工作表"""
    try:
        ss = get_spreadsheet()
        ws = ss.worksheet(sheet_name)
        ws.append_row(row_data, value_input_option='USER_ENTERED')
        return True
    except Exception as e:
        st.error(f"寫入失敗：{e}")
        return False


def delete_record(sheet_name, row_index):
    """刪除指定工作表的某一列（row_index 為 1-based，含標題列）"""
    try:
        ss = get_spreadsheet()
        ws = ss.worksheet(sheet_name)
        ws.delete_rows(row_index)
        return True
    except Exception as e:
        st.error(f"刪除失敗：{e}")
        return False


def generate_id():
    """產生唯一 ID"""
    return str(int(time.time() * 1000))


# --- 主畫面 ---
st.title("🏢 漢平世家")
st.caption("警衛收款系統")

page = st.selectbox(
    "功能選擇",
    ["💰 收款登記", "🧾 代墊支出", "📊 本月對帳報告", "📋 收款紀錄查詢"],
    label_visibility="collapsed"
)

# ==========================================
# 💰 收款登記
# ==========================================
if page == "💰 收款登記":
    st.header("💰 收款登記")

    residents = get_residents()
    if not residents:
        st.warning("無法讀取住戶清單，請確認 Google Sheet 設定。")
        st.stop()

    # 住戶選擇
    resident_options = [f"{r['地址']} - {r['姓名']}" for r in residents]
    selected_idx = st.selectbox("選擇住戶", range(len(resident_options)),
                                format_func=lambda i: resident_options[i])
    selected_resident = residents[selected_idx]
    monthly_fee = int(selected_resident['金額'])
    st.info(f"📍 {selected_resident['地址']} {selected_resident['姓名']}　月費：**${monthly_fee:,}**")

    # 收款月份
    today = date.today()
    col_y, col_m = st.columns(2)
    with col_y:
        collect_year = st.number_input("收款年份", value=today.year, step=1,
                                       min_value=2024, max_value=2030)
    with col_m:
        collect_month = st.number_input("收款月份", value=today.month, step=1,
                                         min_value=1, max_value=12)

    # 繳費類型
    pay_type = st.radio(
        "繳費類型",
        ["當月管理費", "補繳欠款", "預繳下月"],
        horizontal=True
    )

    # 繳費月份
    if pay_type == "當月管理費":
        pay_months = [collect_month]
        st.write(f"繳費月份：**{collect_month}月**")
    elif pay_type == "補繳欠款":
        all_months = list(range(1, 13))
        pay_months = st.multiselect(
            "選擇補繳月份（可多選）",
            all_months,
            format_func=lambda m: f"{m}月"
        )
        if not pay_months:
            st.warning("請選擇補繳的月份")
    elif pay_type == "預繳下月":
        next_month = collect_month + 1 if collect_month < 12 else 1
        next_year = collect_year if collect_month < 12 else collect_year + 1
        # 可選擇預繳幾個月
        prepay_count = st.number_input("預繳月數", value=1, min_value=1, max_value=6, step=1)
        pay_months = []
        for i in range(prepay_count):
            m = collect_month + 1 + i
            if m > 12:
                m -= 12
            pay_months.append(m)
        months_str = "、".join([f"{m}月" for m in pay_months])
        st.write(f"預繳月份：**{months_str}**")

    # 金額
    total_amount = monthly_fee * len(pay_months) if pay_months else 0
    amount = st.number_input("金額", value=total_amount, step=100, min_value=0)

    # 照片
    st.subheader("📷 拍照存證")
    photo_tab1, photo_tab2 = st.tabs(["📸 拍照", "📁 上傳檔案"])
    photo_data = None
    with photo_tab1:
        camera_photo = st.camera_input("拍照", label_visibility="collapsed")
        if camera_photo:
            photo_data = camera_photo.getvalue()
    with photo_tab2:
        uploaded_file = st.file_uploader("上傳照片", type=["jpg", "jpeg", "png"],
                                          label_visibility="collapsed")
        if uploaded_file:
            photo_data = uploaded_file.getvalue()

    # 備註
    note = st.text_area("備註", placeholder="（選填）", height=80)

    # 送出
    st.divider()
    if st.button("✅ 確認送出", type="primary", use_container_width=True):
        if not pay_months:
            st.error("請選擇繳費月份！")
        elif amount <= 0:
            st.error("金額必須大於 0！")
        else:
            with st.spinner("送出中..."):
                # 上傳照片到 Drive
                photo_link = ""
                if photo_data:
                    compressed = compress_image(photo_data)
                    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                    filename = f"{selected_resident['地址']}_{selected_resident['姓名']}_{ts}.jpg"
                    photo_link = upload_photo_to_drive(compressed, filename)

                # 寫入收款紀錄
                record_id = generate_id()
                pay_months_str = ",".join([str(m) for m in pay_months])
                row = [
                    record_id,
                    today.strftime("%Y-%m-%d"),
                    int(selected_resident['編號']),
                    selected_resident['姓名'],
                    selected_resident['地址'],
                    int(collect_year),
                    int(collect_month),
                    pay_type,
                    pay_months_str,
                    int(amount),
                    note,
                    photo_link,
                    ""  # 已匯入欄位留空
                ]
                if append_record("收款紀錄", row):
                    st.success(f"✅ 已登記！{selected_resident['地址']} {selected_resident['姓名']} ${amount:,}")
                    st.balloons()
                else:
                    st.error("寫入失敗，請重試。")

# ==========================================
# 🧾 代墊支出
# ==========================================
elif page == "🧾 代墊支出":
    st.header("🧾 代墊支出登記")

    today = date.today()
    expense_date = st.date_input("日期", value=today)
    item = st.text_input("項目", placeholder="例如：垃圾袋、燈管...")
    expense_amount = st.number_input("金額", value=0, step=100, min_value=0)

    # 照片
    st.subheader("📷 收據照片")
    photo_tab1, photo_tab2 = st.tabs(["📸 拍照", "📁 上傳檔案"])
    expense_photo = None
    with photo_tab1:
        cam = st.camera_input("拍照", key="expense_cam", label_visibility="collapsed")
        if cam:
            expense_photo = cam.getvalue()
    with photo_tab2:
        upl = st.file_uploader("上傳照片", type=["jpg", "jpeg", "png"],
                                key="expense_upload", label_visibility="collapsed")
        if upl:
            expense_photo = upl.getvalue()

    expense_note = st.text_area("備註", placeholder="（選填）", key="expense_note", height=80)

    st.divider()
    if st.button("✅ 確認送出", type="primary", use_container_width=True, key="expense_submit"):
        if not item:
            st.error("請填寫項目名稱！")
        elif expense_amount <= 0:
            st.error("金額必須大於 0！")
        else:
            with st.spinner("送出中..."):
                photo_link = ""
                if expense_photo:
                    compressed = compress_image(expense_photo)
                    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                    filename = f"代墊_{item}_{ts}.jpg"
                    photo_link = upload_photo_to_drive(compressed, filename)

                record_id = generate_id()
                row = [
                    record_id,
                    expense_date.strftime("%Y-%m-%d"),
                    item,
                    int(expense_amount),
                    expense_note,
                    photo_link
                ]
                if append_record("代墊支出", row):
                    st.success(f"✅ 已登記！{item} ${expense_amount:,}")
                    st.balloons()
                else:
                    st.error("寫入失敗，請重試。")

# ==========================================
# 📊 本月對帳報告
# ==========================================
elif page == "📊 本月對帳報告":
    st.header("📊 對帳報告")

    today = date.today()
    col_ry, col_rm = st.columns(2)
    with col_ry:
        report_year = st.number_input("年份", value=today.year, step=1,
                                       min_value=2024, max_value=2030, key="report_y")
    with col_rm:
        report_month = st.number_input("月份", value=today.month, step=1,
                                        min_value=1, max_value=12, key="report_m")

    if st.button("📊 產生報告", use_container_width=True):
        with st.spinner("讀取資料中..."):
            records = get_records("收款紀錄")
            expenses = get_records("代墊支出")

        # 篩選當月收款紀錄
        month_records = [
            r for r in records
            if int(r.get('收款年份', 0)) == report_year
            and int(r.get('收款月份', 0)) == report_month
        ]

        # 篩選當月代墊支出
        month_expenses = [
            e for e in expenses
            if e.get('日期', '').startswith(f"{report_year}-{report_month:02d}")
        ]

        st.subheader(f"📅 {report_year}年{report_month}月 收款對帳")
        st.divider()

        # 分類整理
        current_month_payments = []   # 當月管理費
        late_payments = []            # 補繳欠款
        prepaid_payments = []         # 預繳下月

        for r in month_records:
            pay_type = r.get('繳費類型', '')
            if pay_type == '當月管理費':
                current_month_payments.append(r)
            elif pay_type == '補繳欠款':
                late_payments.append(r)
            elif pay_type == '預繳下月':
                prepaid_payments.append(r)

        # 當月管理費
        st.markdown("### 【當月管理費】")
        if current_month_payments:
            total_current = sum(int(r.get('金額', 0)) for r in current_month_payments)
            st.markdown(f"**{len(current_month_payments)} 戶已收　${total_current:,}**")
            for r in current_month_payments:
                st.markdown(f"- {r.get('地址', '')} {r.get('住戶姓名', '')}　${int(r.get('金額', 0)):,}")
        else:
            st.markdown("_無_")

        # 補繳欠款
        st.markdown("### 【補繳欠款】")
        if late_payments:
            total_late = sum(int(r.get('金額', 0)) for r in late_payments)
            st.markdown(f"**{len(late_payments)} 戶　${total_late:,}**")
            for r in late_payments:
                months_str = r.get('繳費月份', '')
                st.markdown(
                    f"- {r.get('地址', '')} {r.get('住戶姓名', '')}　"
                    f"${int(r.get('金額', 0)):,}（{months_str}月）"
                )
        else:
            st.markdown("_無_")

        # 預繳下月
        st.markdown("### 【預繳下月】")
        if prepaid_payments:
            total_prepaid = sum(int(r.get('金額', 0)) for r in prepaid_payments)
            st.markdown(f"**{len(prepaid_payments)} 戶　${total_prepaid:,}**")
            for r in prepaid_payments:
                months_str = r.get('繳費月份', '')
                st.markdown(
                    f"- {r.get('地址', '')} {r.get('住戶姓名', '')}　"
                    f"${int(r.get('金額', 0)):,}（{months_str}月）"
                )
        else:
            st.markdown("_無_")

        # 代墊支出
        st.markdown("### 【代墊支出】")
        if month_expenses:
            total_expense = sum(int(e.get('金額', 0)) for e in month_expenses)
            st.markdown(f"**{len(month_expenses)} 筆　${total_expense:,}**")
            for e in month_expenses:
                st.markdown(f"- {e.get('項目', '')}　${int(e.get('金額', 0)):,}")
        else:
            total_expense = 0
            st.markdown("_無_")

        # 彙總
        st.divider()
        total_income = sum(int(r.get('金額', 0)) for r in month_records)
        net = total_income - total_expense
        st.markdown(f"""
**當月實收總額：${total_income:,}**

**代墊支出合計：${total_expense:,}**

**應交給管理員：${net:,}**
""")

# ==========================================
# 📋 收款紀錄查詢
# ==========================================
elif page == "📋 收款紀錄查詢":
    st.header("📋 收款紀錄查詢")

    today = date.today()
    col_qy, col_qm = st.columns(2)
    with col_qy:
        query_year = st.number_input("年份", value=today.year, step=1,
                                      min_value=2024, max_value=2030, key="query_y")
    with col_qm:
        query_month = st.number_input("月份", value=today.month, step=1,
                                       min_value=1, max_value=12, key="query_m")

    query_type = st.selectbox("查詢類別", ["全部", "收款紀錄", "代墊支出"])

    if query_type in ["全部", "收款紀錄"]:
        st.subheader("💰 收款紀錄")
        records = get_records("收款紀錄")
        filtered = [
            r for r in records
            if int(r.get('收款年份', 0)) == query_year
            and int(r.get('收款月份', 0)) == query_month
        ]
        if filtered:
            for i, r in enumerate(filtered):
                with st.expander(
                    f"{r.get('日期', '')} | {r.get('地址', '')} {r.get('住戶姓名', '')} "
                    f"| {r.get('繳費類型', '')} | ${int(r.get('金額', 0)):,}"
                ):
                    st.write(f"**繳費月份：** {r.get('繳費月份', '')}月")
                    if r.get('備註'):
                        st.write(f"**備註：** {r['備註']}")
                    if r.get('照片連結'):
                        st.markdown(f"[📷 查看照片]({r['照片連結']})")
                    imported = r.get('已匯入', '')
                    if imported:
                        st.success(f"已匯入：{imported}")
                    else:
                        st.caption("尚未匯入")

                    # 刪除功能
                    # row_index = 標題列(1) + 在全部紀錄中的位置
                    # 找到此筆紀錄在全部 records 中的 index
                    rec_id = r.get('ID', '')
                    if rec_id and st.button(f"🗑️ 刪除此筆", key=f"del_{rec_id}"):
                        # 找出在 sheet 中的列號（1-based，含標題列）
                        all_records = get_records("收款紀錄")
                        for idx, ar in enumerate(all_records):
                            if str(ar.get('ID', '')) == str(rec_id):
                                if delete_record("收款紀錄", idx + 2):  # +2: 標題列+0-based
                                    st.success("已刪除！")
                                    st.rerun()
                                break
        else:
            st.info("此月份無收款紀錄")

    if query_type in ["全部", "代墊支出"]:
        st.subheader("🧾 代墊支出")
        expenses = get_records("代墊支出")
        filtered_exp = [
            e for e in expenses
            if e.get('日期', '').startswith(f"{query_year}-{query_month:02d}")
        ]
        if filtered_exp:
            for e in filtered_exp:
                with st.expander(
                    f"{e.get('日期', '')} | {e.get('項目', '')} | ${int(e.get('金額', 0)):,}"
                ):
                    if e.get('備註'):
                        st.write(f"**備註：** {e['備註']}")
                    if e.get('照片連結'):
                        st.markdown(f"[📷 查看收據]({e['照片連結']})")

                    rec_id = e.get('ID', '')
                    if rec_id and st.button(f"🗑️ 刪除此筆", key=f"del_exp_{rec_id}"):
                        all_expenses = get_records("代墊支出")
                        for idx, ae in enumerate(all_expenses):
                            if str(ae.get('ID', '')) == str(rec_id):
                                if delete_record("代墊支出", idx + 2):
                                    st.success("已刪除！")
                                    st.rerun()
                                break
        else:
            st.info("此月份無代墊支出")
