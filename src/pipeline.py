from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Iterable

import pandas as pd


ACTIVITY_TYPES = {"post", "comment", "reaction", "like"}

QUESTION_TERMS = (
    "giá", "bao nhiêu", "chi phí", "phí", "mua ở đâu", "đặt hàng", "đặt lịch",
    "còn hàng", "ship", "giao hàng", "tư vấn", "ib", "inbox", "liên hệ",
    "how much", "price", "buy", "available", "shipping",
)
EXPERIENCE_TERMS = (
    "đã mua", "đã dùng", "đang dùng", "mình dùng", "tôi dùng", "trải nghiệm",
    "hiệu quả", "kết quả", "dùng rồi", "bought", "used", "experience", "result",
)
SALES_TERMS = (
    "mình bán", "tôi bán", "bên mình", "shop mình", "đại lý", "sỉ", "sale",
    "khuyến mãi", "combo", "inbox mình", "liên hệ mình", "ib mình", "đặt đơn",
    "we sell", "our shop", "discount", "wholesale",
)
CONTACT_TERMS = ("zalo", "sđt", "sdt", "điện thoại", "hotline", "telegram", "website")
NEGATION_TERMS = ("không phải", "chưa", "không bán", "not selling")


@dataclass
class Activity:
    activity_id: str
    account_id: str
    account_name: str
    activity_type: str
    content: str
    post_id: str
    post_url: str
    created_at: str
    reaction_type: str
    group_name: str


@dataclass
class Classification:
    label: str
    confidence: float
    customer_score: float
    advisor_score: float
    reasons: list[str]
    needs_human_review: bool


def _clean(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value).strip()


def _first(item: dict[str, Any], *keys: str) -> str:
    for key in keys:
        if key in item and _clean(item[key]):
            return _clean(item[key])
    return ""


def _normalise_type(value: str) -> str:
    value = value.lower().strip()
    if value in {"post", "posts", "status"}:
        return "post"
    if value in {"comment", "comments", "reply"}:
        return "comment"
    if value in {"reaction", "reactions", "like", "likes", "love", "haha", "wow", "sad", "angry"}:
        return "reaction"
    return value or "comment"


def _activity_from_item(item: dict[str, Any], *, activity_type: str | None = None,
                        post_id: str = "", group_name: str = "") -> Activity:
    activity_type = _normalise_type(activity_type or _first(item, "activity_type", "type", "kind"))
    resolved_post_id = post_id or _first(item, "post_id", "postId", "id")
    author = item.get("from") or item.get("author") or item.get("user")
    author = author if isinstance(author, dict) else {}
    account_id = _first(item, "account_id", "accountId", "author_id", "from_id", "user_id") or _first(author, "id", "user_id")
    account_name = _first(item, "account_name", "accountName", "author_name", "from_name", "name", "username") or _first(author, "name", "username")
    content = _first(item, "content", "message", "text", "caption", "body")
    return Activity(
        activity_id=_first(item, "activity_id", "activityId", "comment_id", "id") or hashlib.sha1(
            f"{account_id}|{resolved_post_id}|{activity_type}|{content}".encode("utf-8")
        ).hexdigest()[:16],
        account_id=account_id or account_name or "unknown",
        account_name=account_name or account_id or "Unknown",
        activity_type=activity_type if activity_type in ACTIVITY_TYPES else "comment",
        content=content,
        post_id=resolved_post_id,
        post_url=_first(item, "post_url", "postUrl", "url", "permalink_url", "permalink"),
        created_at=_first(item, "created_at", "createdAt", "timestamp", "created_time", "published_at"),
        reaction_type=_first(item, "reaction_type", "reactionType", "type") if activity_type == "reaction" else "",
        group_name=group_name or _first(item, "group_name", "groupName", "group"),
    )


def _iter_nested(payload: Any) -> Iterable[Activity]:
    """Accept flat exports and common nested post/comment/reaction JSON shapes."""
    if isinstance(payload, list):
        for item in payload:
            if isinstance(item, dict):
                yield _activity_from_item(item)
        return
    if not isinstance(payload, dict):
        return

    default_group = _first(payload, "group_name", "groupName", "group")
    activities = payload.get("activities") or payload.get("data")
    if isinstance(activities, list):
        for item in activities:
            if isinstance(item, dict):
                yield _activity_from_item(item, group_name=default_group)
        return

    posts = payload.get("posts") or payload.get("feed") or []
    if isinstance(posts, dict):
        posts = posts.get("data", [])
    for post in posts:
        if not isinstance(post, dict):
            continue
        post_activity = _activity_from_item(post, activity_type="post", group_name=default_group)
        yield post_activity
        post_id = post_activity.post_id
        comments = post.get("comments", [])
        if isinstance(comments, dict):
            comments = comments.get("data", [])
        for comment in comments or []:
            if isinstance(comment, dict):
                yield _activity_from_item(comment, activity_type="comment", post_id=post_id, group_name=default_group)
        reactions = post.get("reactions", [])
        if isinstance(reactions, dict):
            reactions = reactions.get("data", [])
        for reaction in reactions or []:
            if isinstance(reaction, dict):
                yield _activity_from_item(reaction, activity_type="reaction", post_id=post_id, group_name=default_group)


def load_payload(raw: bytes, filename: str) -> list[Activity]:
    suffix = filename.lower().rsplit(".", 1)[-1]
    if suffix == "csv":
        frame = pd.read_csv(pd.io.common.BytesIO(raw))
        payload: Any = frame.fillna("").to_dict(orient="records")
    elif suffix in {"json", "jsonl"}:
        text = raw.decode("utf-8-sig")
        if suffix == "jsonl":
            payload = [json.loads(line) for line in text.splitlines() if line.strip()]
        else:
            payload = json.loads(text)
    else:
        raise ValueError("Chỉ hỗ trợ tệp CSV, JSON hoặc JSONL.")
    activities = list(_iter_nested(payload))
    if not activities:
        raise ValueError("Không tìm thấy activity hợp lệ trong tệp dữ liệu.")
    return deduplicate(activities)


def deduplicate(activities: Iterable[Activity]) -> list[Activity]:
    result: list[Activity] = []
    seen: set[tuple[str, str]] = set()
    for activity in activities:
        key = (activity.activity_id, activity.activity_type)
        if key in seen:
            continue
        seen.add(key)
        result.append(activity)
    return result


def _contains(text: str, terms: Iterable[str]) -> bool:
    lowered = text.lower()
    return any(term in lowered for term in terms)


def _count(texts: Iterable[str], terms: Iterable[str]) -> int:
    return sum(1 for text in texts if _contains(text, terms))


def anonymize_account(account_id: str, salt: str = "local-analysis") -> str:
    digest = hashlib.sha256(f"{salt}:{account_id}".encode("utf-8")).hexdigest()[:12]
    return f"account_{digest}"


def build_account_features(activities: Iterable[Activity], *, anonymize: bool = True,
                           salt: str = "local-analysis") -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    grouped: dict[str, list[Activity]] = {}
    for activity in activities:
        grouped.setdefault(activity.account_id, []).append(activity)

    for account_id, account_activities in grouped.items():
        texts = [a.content for a in account_activities if a.content]
        comment_texts = [a.content for a in account_activities if a.activity_type in {"post", "comment"}]
        questions = _count(comment_texts, QUESTION_TERMS)
        experiences = _count(comment_texts, EXPERIENCE_TERMS)
        sales = _count(comment_texts, SALES_TERMS)
        contacts = _count(comment_texts, CONTACT_TERMS)
        negations = _count(comment_texts, NEGATION_TERMS)
        posts = sum(a.activity_type == "post" for a in account_activities)
        comments = sum(a.activity_type == "comment" for a in account_activities)
        reactions = sum(a.activity_type == "reaction" for a in account_activities)
        customer_score = min(100.0, questions * 15 + experiences * 17 + comments * 2 + posts * 2)
        advisor_score = min(100.0, max(0, sales * 22 + contacts * 12 + posts * 5 - negations * 8))
        if experiences >= 2 and customer_score >= 25 and advisor_score < 45:
            heuristic_label = "real_customer"
        elif customer_score >= advisor_score + 15 and customer_score >= 25:
            heuristic_label = "potential_customer"
        elif advisor_score >= customer_score + 15 and advisor_score >= 25:
            heuristic_label = "advisor_or_seller"
        elif max(customer_score, advisor_score) < 25:
            heuristic_label = "general_member"
        else:
            heuristic_label = "uncertain"
        rows.append({
            "account_id": anonymize_account(account_id, salt) if anonymize else account_id,
            "account_name": "Anonymous" if anonymize else next((a.account_name for a in account_activities if a.account_name), "Unknown"),
            "posts": posts,
            "comments": comments,
            "reactions": reactions,
            "total_activities": len(account_activities),
            "questions": questions,
            "experience_signals": experiences,
            "sales_signals": sales,
            "contact_signals": contacts,
            "customer_score": round(customer_score, 1),
            "advisor_score": round(advisor_score, 1),
            "heuristic_label": heuristic_label,
            "sample_content": " | ".join(texts[:5]),
            "last_activity": max((a.created_at for a in account_activities), default=""),
            "group_name": next((a.group_name for a in account_activities if a.group_name), ""),
        })
    return pd.DataFrame(rows).sort_values("total_activities", ascending=False).reset_index(drop=True)


def classify_with_rules(features: pd.DataFrame) -> pd.DataFrame:
    result = features.copy()
    result["label"] = result["heuristic_label"]
    result["confidence"] = (result[["customer_score", "advisor_score"]].max(axis=1) / 100).clip(0.2, 0.95).round(2)
    result["reasons"] = result.apply(_reason_row, axis=1)
    result["needs_human_review"] = result["label"].eq("uncertain") | result["confidence"].lt(0.55)
    return result


def _reason_row(row: pd.Series) -> str:
    reasons = []
    if row["questions"]:
        reasons.append(f"{int(row['questions'])} tín hiệu hỏi mua/giá")
    if row["experience_signals"]:
        reasons.append(f"{int(row['experience_signals'])} tín hiệu trải nghiệm")
    if row["sales_signals"]:
        reasons.append(f"{int(row['sales_signals'])} tín hiệu bán/tư vấn")
    if row["contact_signals"]:
        reasons.append(f"{int(row['contact_signals'])} tín hiệu liên hệ")
    return "; ".join(reasons) or "Chưa có tín hiệu nội dung rõ ràng"


def _ai_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "label": {"type": "string", "enum": ["real_customer", "potential_customer", "advisor_or_seller", "general_member", "uncertain"]},
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            "reasons": {"type": "array", "items": {"type": "string"}},
            "needs_human_review": {"type": "boolean"},
        },
        "required": ["label", "confidence", "reasons", "needs_human_review"],
    }


def classify_with_openai(features: pd.DataFrame, *, model: str | None = None,
                         max_accounts: int = 50) -> pd.DataFrame:
    """Classify a bounded number of accounts; leaves the rest on rules."""
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("Chưa có OPENAI_API_KEY trong biến môi trường hoặc Streamlit secrets.")
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise RuntimeError("Cài dependency bằng: pip install -r requirements.txt") from exc

    client = OpenAI(api_key=api_key)
    output = classify_with_rules(features)
    chosen_model = model or os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
    for index, row in output.head(max_accounts).iterrows():
        prompt = {
            "account_id": row["account_id"],
            "activity_summary": {
                "posts": int(row["posts"]),
                "comments": int(row["comments"]),
                "reactions": int(row["reactions"]),
                "questions": int(row["questions"]),
                "experience_signals": int(row["experience_signals"]),
                "sales_signals": int(row["sales_signals"]),
                "contact_signals": int(row["contact_signals"]),
                "sample_content": row["sample_content"],
            },
        }
        response = client.responses.create(
            model=chosen_model,
            input=[
                {"role": "system", "content": [{"type": "input_text", "text": (
                    "Bạn là bộ phân loại lead. Chỉ phân loại dựa trên dữ liệu được cung cấp. "
                    "Không suy đoán giới tính, tuổi, thu nhập, sức khỏe hay danh tính ngoài dữ liệu. "
                    "Một lượt like đơn lẻ không đủ để kết luận khách hàng. Nếu thiếu bằng chứng, chọn uncertain."
                )}]},
                {"role": "user", "content": [{"type": "input_text", "text": json.dumps(prompt, ensure_ascii=False)}]},
            ],
            text={"format": {"type": "json_schema", "name": "account_classification", "strict": True, "schema": _ai_schema()}},
        )
        parsed = json.loads(response.output_text)
        output.at[index, "label"] = parsed["label"]
        output.at[index, "confidence"] = round(float(parsed["confidence"]), 2)
        output.at[index, "reasons"] = "; ".join(parsed["reasons"])
        output.at[index, "needs_human_review"] = bool(parsed["needs_human_review"])
    output["ai_model"] = chosen_model
    return output


def activities_frame(activities: Iterable[Activity], *, anonymize: bool = True,
                     salt: str = "local-analysis") -> pd.DataFrame:
    rows = []
    for activity in activities:
        row = asdict(activity)
        if anonymize:
            row["account_id"] = anonymize_account(activity.account_id, salt)
            row["account_name"] = "Anonymous"
        rows.append(row)
    return pd.DataFrame(rows)


def demo_activities() -> list[Activity]:
    raw = [
        {"activity_id": "p1", "account_id": "a1", "account_name": "Lan", "activity_type": "post", "content": "Mọi người cho mình hỏi giá liệu trình và có giao hàng không?", "post_id": "p1", "created_at": "2026-09-27", "group_name": "Demo group"},
        {"activity_id": "c1", "account_id": "a1", "account_name": "Lan", "activity_type": "comment", "content": "Mình cần tư vấn, ngân sách khoảng bao nhiêu?", "post_id": "p2", "created_at": "2026-09-27", "group_name": "Demo group"},
        {"activity_id": "r1", "account_id": "a1", "account_name": "Lan", "activity_type": "reaction", "reaction_type": "like", "post_id": "p2", "created_at": "2026-09-27", "group_name": "Demo group"},
        {"activity_id": "p3", "account_id": "a2", "account_name": "Mai Shop", "activity_type": "post", "content": "Shop mình có combo khuyến mãi, ib mình để được báo giá và đặt đơn.", "post_id": "p3", "created_at": "2026-09-26", "group_name": "Demo group"},
        {"activity_id": "c3", "account_id": "a2", "account_name": "Mai Shop", "activity_type": "comment", "content": "Bên mình bán sản phẩm chính hãng, liên hệ Zalo để nhận sale.", "post_id": "p4", "created_at": "2026-09-26", "group_name": "Demo group"},
        {"activity_id": "c4", "account_id": "a3", "account_name": "Hương", "activity_type": "comment", "content": "Mình đã dùng rồi, hiệu quả khá tốt sau 2 tuần.", "post_id": "p3", "created_at": "2026-09-25", "group_name": "Demo group"},
        {"activity_id": "c5", "account_id": "a3", "account_name": "Hương", "activity_type": "comment", "content": "Mình dùng sản phẩm này rồi, kết quả ổn.", "post_id": "p5", "created_at": "2026-09-24", "group_name": "Demo group"},
        {"activity_id": "r5", "account_id": "a4", "account_name": "Nam", "activity_type": "reaction", "reaction_type": "like", "post_id": "p5", "created_at": "2026-09-24", "group_name": "Demo group"},
    ]
    return [_activity_from_item(item) for item in raw]
