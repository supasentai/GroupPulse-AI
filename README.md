# Group Activity Intelligence

Ứng dụng Python + Streamlit để phân tích dữ liệu bài viết, bình luận và reaction đã được cấp quyền hoặc xuất hợp lệ từ một group.

## Chạy local

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
streamlit run app.py
```

Mở URL Streamlit được hiển thị trong terminal.

## Định dạng dữ liệu

### CSV phẳng

Các cột được hỗ trợ gồm:

```text
activity_id,account_id,account_name,activity_type,content,post_id,post_url,created_at,reaction_type,group_name
```

`activity_type` nhận `post`, `comment`, `reaction` hoặc `like`. Một số tên cột thay thế phổ biến như `message`, `text`, `author_id`, `author_name`, `timestamp` cũng được tự nhận diện.

### JSON lồng

Có thể dùng payload dạng:

```json
{
  "group_name": "My group",
  "posts": [
    {
      "id": "post-1",
      "message": "Nội dung bài viết",
      "from": {"id": "user-1", "name": "Member"},
      "comments": {"data": [{"id": "comment-1", "message": "Bình luận"}]},
      "reactions": {"data": [{"id": "user-2", "type": "LIKE"}]}
    }
  ]
}
```

## AI

Không bật AI thì app dùng heuristic cục bộ. Để bật AI, đặt biến môi trường:

```powershell
$env:OPENAI_API_KEY = "your-key"
$env:OPENAI_MODEL = "gpt-4.1-mini"
streamlit run app.py
```

AI chỉ nhận bản tóm tắt account và một số nội dung mẫu. App mặc định ẩn danh account trước khi hiển thị và gửi dữ liệu phân tích.

## Phân loại

- `real_customer`: có nhiều tín hiệu trải nghiệm/sử dụng.
- `potential_customer`: hỏi giá, tư vấn, mua hàng hoặc giao hàng.
- `advisor_or_seller`: có tín hiệu bán, báo giá, shop hoặc liên hệ thương mại.
- `general_member`: chưa có tín hiệu rõ.
- `uncertain`: mâu thuẫn hoặc chưa đủ dữ liệu.

Đây là hệ thống hỗ trợ phân tích, không phải kết luận chắc chắn. Không tự động gửi comment/DM hay quyết định loại trừ người dùng.

## Ranh giới sử dụng

App này không chứa scraper Facebook, không dùng cookie/mật khẩu, không bypass CAPTCHA và không né giới hạn nền tảng. Collector nên được nối với API, export hoặc nguồn dữ liệu mà bạn có quyền sử dụng.

