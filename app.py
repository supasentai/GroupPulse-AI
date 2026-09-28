from __future__ import annotations

import os
from io import BytesIO

import pandas as pd
import streamlit as st

from src.pipeline import (
    activities_frame,
    build_account_features,
    classify_with_openai,
    classify_with_rules,
    demo_activities,
    load_payload,
)


st.set_page_config(page_title="Group Activity Intelligence", page_icon="📊", layout="wide")

st.title("Group Activity Intelligence")
st.caption("Phân tích dữ liệu group đã được cấp quyền; mặc định ẩn danh account và không tự động tương tác lại với thành viên.")

with st.sidebar:
    st.header("Nguồn dữ liệu")
    uploaded = st.file_uploader("Tải JSON, JSONL hoặc CSV", type=["json", "jsonl", "csv"])
    use_demo = st.checkbox("Dùng dữ liệu demo", value=uploaded is None)
    st.divider()
    anonymize = st.checkbox("Ẩn danh account", value=True, help="Không hiển thị tên/ID thật trong dashboard và file xuất.")
    salt = st.text_input("Mã salt cục bộ", value="local-analysis", type="password") or "local-analysis"
    st.divider()
    enable_ai = st.checkbox("Gọi AI để phân loại", value=False)
    ai_model = st.text_input("Model AI", value=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"))
    ai_limit = st.number_input("Số account gửi AI tối đa", min_value=1, max_value=500, value=50, step=1)
    st.caption("AI chỉ nhận bản tóm tắt hành vi và nội dung mẫu; nên kiểm tra các kết quả độ tin cậy thấp.")


@st.cache_data(show_spinner=False)
def analyze(raw: bytes | None, filename: str, demo: bool, anonymize_flag: bool, salt_value: str,
            use_ai: bool, model: str, limit: int):
    if demo:
        activities = demo_activities()
    else:
        if raw is None:
            raise ValueError("Hãy tải tệp dữ liệu hoặc bật dữ liệu demo.")
        activities = load_payload(raw, filename)
    feature_frame = build_account_features(activities, anonymize=anonymize_flag, salt=salt_value)
    if use_ai:
        classified = classify_with_openai(feature_frame, model=model, max_accounts=int(limit))
    else:
        classified = classify_with_rules(feature_frame)
    activity_frame = activities_frame(activities, anonymize=anonymize_flag, salt=salt_value)
    return classified, activity_frame


if st.button("Phân tích dữ liệu", type="primary"):
    st.cache_data.clear()
    try:
        with st.spinner("Đang chuẩn hóa và phân tích..."):
            st.session_state["analysis"] = analyze(
                uploaded.getvalue() if uploaded else None,
                uploaded.name if uploaded else "demo.json",
                use_demo,
                anonymize,
                salt,
                enable_ai,
                ai_model,
                int(ai_limit),
            )
        st.success("Đã phân tích xong.")
    except Exception as exc:
        st.error(str(exc))


if "analysis" not in st.session_state:
    st.info("Chọn dữ liệu ở thanh bên rồi bấm “Phân tích dữ liệu”.")
    st.stop()

accounts, activities = st.session_state["analysis"]

total_activities = len(activities)
total_accounts = len(accounts)
total_posts = int((activities["activity_type"] == "post").sum()) if not activities.empty else 0
total_comments = int((activities["activity_type"] == "comment").sum()) if not activities.empty else 0

metric_cols = st.columns(4)
metric_cols[0].metric("Accounts", f"{total_accounts:,}")
metric_cols[1].metric("Activities", f"{total_activities:,}")
metric_cols[2].metric("Posts", f"{total_posts:,}")
metric_cols[3].metric("Comments", f"{total_comments:,}")

tab_overview, tab_accounts, tab_activities, tab_export = st.tabs(["Tổng quan", "Accounts", "Hoạt động", "Xuất báo cáo"])

with tab_overview:
    st.subheader("Phân loại account")
    label_counts = accounts["label"].value_counts().rename_axis("label").to_frame("accounts")
    st.bar_chart(label_counts)
    col_a, col_b = st.columns(2)
    with col_a:
        st.subheader("Top account theo hoạt động")
        st.dataframe(accounts[["account_id", "label", "total_activities", "customer_score", "advisor_score"]].head(10), use_container_width=True, hide_index=True)
    with col_b:
        st.subheader("Tín hiệu hành vi")
        signal_cols = ["questions", "experience_signals", "sales_signals", "contact_signals"]
        st.bar_chart(accounts[signal_cols].sum().rename("count"))

with tab_accounts:
    st.subheader("Danh sách account")
    labels = ["Tất cả"] + sorted(accounts["label"].dropna().unique().tolist())
    selected_label = st.selectbox("Lọc theo phân loại", labels)
    min_conf = st.slider("Độ tin cậy tối thiểu", 0.0, 1.0, 0.0, 0.05)
    view = accounts.copy()
    if selected_label != "Tất cả":
        view = view[view["label"] == selected_label]
    view = view[view["confidence"] >= min_conf]
    st.dataframe(view, use_container_width=True, hide_index=True)

with tab_activities:
    st.subheader("Bài viết, comment và reaction")
    activity_types = st.multiselect("Loại hoạt động", sorted(activities["activity_type"].unique()), default=sorted(activities["activity_type"].unique()))
    activity_view = activities[activities["activity_type"].isin(activity_types)]
    st.dataframe(activity_view, use_container_width=True, hide_index=True)

with tab_export:
    st.subheader("Tải báo cáo")
    account_csv = accounts.to_csv(index=False).encode("utf-8-sig")
    activity_csv = activities.to_csv(index=False).encode("utf-8-sig")
    st.download_button("Tải account_analysis.csv", account_csv, "account_analysis.csv", "text/csv")
    st.download_button("Tải activities.csv", activity_csv, "activities.csv", "text/csv")
    st.download_button("Tải report.json", accounts.to_json(orient="records", force_ascii=False, indent=2).encode("utf-8"), "report.json", "application/json")

st.divider()
st.caption("Phân loại là tín hiệu hỗ trợ quyết định, không phải kết luận chắc chắn về danh tính hoặc trạng thái mua hàng của một người.")

