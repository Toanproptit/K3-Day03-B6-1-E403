"""
🛠️ TOOL REGISTRY & SCHEMAS (Dành cho Role 2: Tool & Spec Engineer)

Bốn "món đồ nghề" mà ReAct Agent gọi được, tất cả đều đi qua HTTP tới API cho thuê
đang chạy ở localhost:8000 (xem src/rental_api/server.py).

QUY TẮC CHUNG CHO MỌI TOOL:
    - Luôn trả về chuỗi (str), không bao giờ ném exception ra ngoài.
    - Khi lỗi thì trả chuỗi bắt đầu bằng 'LỖI:' để Agent đọc được và tự suy luận cách chữa.
    - Văn bản trả về viết gọn, mỗi tin một dòng, để không phình transcript của vòng lặp ReAct.
"""

import os

import requests
from dotenv import load_dotenv

load_dotenv()

# Địa chỉ API cho thuê. Đổi sang API thật sau này chỉ cần sửa biến môi trường này.
API_BASE_URL = os.getenv("RENTAL_API_URL", "http://127.0.0.1:8000").rstrip("/")
TIMEOUT_SECONDS = 10

CONNECTION_ERROR = (
    f"LỖI: không kết nối được API cho thuê tại {API_BASE_URL}. "
    "Hãy chắc chắn đã chạy: uvicorn src.rental_api.server:app --port 8000"
)


def _format_age(days_old: int | None) -> str:
    """Diễn giải độ mới của tin đăng cho người đọc."""
    if days_old is None:
        return "không rõ ngày đăng"
    if days_old == 0:
        return "đăng hôm nay"
    if days_old == 1:
        return "đăng hôm qua"
    return f"đăng {days_old} ngày trước"


def _format_listing_line(item: dict) -> str:
    """Rút gọn một tin đăng thành đúng một dòng cho Agent đọc."""
    amenities = ", ".join(item.get("amenities") or []) or "không rõ tiện ích"
    return (
        f"{item['id']} | {item['price_label']} | {item['area_m2']:g}m2 | "
        f"{item['district']} | {_format_age(item.get('days_old'))} | {amenities}"
    )


def _error_from_response(res: requests.Response) -> str:
    """Chuyển lỗi HTTP thành thông báo tiếng Việt mà Agent hiểu được."""
    try:
        detail = res.json().get("detail")
    except Exception:
        detail = None
    if isinstance(detail, list) and detail:
        # Lỗi validate của FastAPI trả về dạng danh sách
        detail = "; ".join(str(d.get("msg", d)) for d in detail)
    return f"LỖI ({res.status_code}): {detail or res.text[:200]}"


def search_listings(district: str, max_price: int, max_days_old: int = None) -> str:
    """
    Tìm phòng trọ / căn hộ cho thuê theo quận và giá thuê tối đa.

    Args:
        district (str): Tên quận ở Hà Nội, có dấu hoặc không dấu đều được
                        (ví dụ: 'Cầu Giấy', 'Cau Giay', 'Thanh Xuân', 'Nam Từ Liêm').
        max_price (int): Giá thuê tối đa mỗi tháng, tính bằng VNĐ (ví dụ: 5000000).
        max_days_old (int, tuỳ chọn): Chỉ lấy tin đăng trong N ngày gần đây.
                        Dùng khi người dùng muốn tin mới, tránh tin cũ đã cho thuê mất.

    Returns:
        str: Tối đa 5 tin, mỗi tin một dòng, tin mới nhất xếp trước.
             Trả 'Không tìm thấy...' nếu không có tin nào khớp điều kiện.
    """
    params = {"district": district, "max_price": max_price, "limit": 5}
    if max_days_old is not None:
        params["max_days_old"] = max_days_old

    try:
        res = requests.get(f"{API_BASE_URL}/listings", params=params, timeout=TIMEOUT_SECONDS)
    except requests.RequestException:
        return CONNECTION_ERROR

    if not res.ok:
        return _error_from_response(res)

    results = res.json().get("results", [])
    if not results:
        filters = f"quận '{district}', giá tối đa {max_price:,}đ"
        if max_days_old is not None:
            filters += f", đăng trong {max_days_old} ngày qua"
        return (
            f"Không tìm thấy tin nào khớp điều kiện ({filters}). "
            "Hãy thử nới giá, đổi quận, hoặc bỏ giới hạn ngày đăng."
        )

    lines = [f"Tìm thấy {len(results)} tin (mới nhất trước):"]
    lines += [f"  {_format_listing_line(item)}" for item in results]
    return "\n".join(lines)


def get_listing_details(listing_id: str) -> str:
    """
    Xem chi tiết đầy đủ của một tin đăng cụ thể.

    Args:
        listing_id (str): Mã tin lấy từ kết quả search_listings (ví dụ: 'pr710261').

    Returns:
        str: Tiêu đề, giá, diện tích, địa chỉ, tiện ích, ngày đăng, mô tả và link gốc.
             Trả 'LỖI (404)...' nếu mã tin không tồn tại.
    """
    try:
        res = requests.get(f"{API_BASE_URL}/listings/{listing_id}", timeout=TIMEOUT_SECONDS)
    except requests.RequestException:
        return CONNECTION_ERROR

    if not res.ok:
        return _error_from_response(res)

    item = res.json()
    amenities = ", ".join(item.get("amenities") or []) or "không rõ"
    return (
        f"Mã tin: {item['id']}\n"
        f"Tiêu đề: {item['title']}\n"
        f"Giá thuê: {item['price_label']}\n"
        f"Diện tích: {item['area_m2']:g} m2\n"
        f"Địa chỉ: {item['address']}\n"
        f"Tiện ích: {amenities}\n"
        f"Thời gian đăng: {_format_age(item.get('days_old'))}\n"
        f"Mô tả: {item['description']}\n"
        f"Link: {item['url']}"
    )


def check_viewing_slots(listing_id: str, date: str) -> str:
    """
    Kiểm tra các khung giờ còn trống để đi xem phòng trong một ngày cụ thể.

    Args:
        listing_id (str): Mã tin đăng (ví dụ: 'pr710261').
        date (str): Ngày muốn xem, bắt buộc định dạng YYYY-MM-DD (ví dụ: '2026-07-29').
                    Chỉ nhận ngày từ hôm nay tới 30 ngày tới.

    Returns:
        str: Danh sách khung giờ còn trống, hoặc thông báo lỗi nếu ngày/mã tin không hợp lệ.
    """
    try:
        res = requests.get(
            f"{API_BASE_URL}/listings/{listing_id}/slots",
            params={"date": date},
            timeout=TIMEOUT_SECONDS,
        )
    except requests.RequestException:
        return CONNECTION_ERROR

    if not res.ok:
        return _error_from_response(res)

    slots = res.json().get("slots", [])
    if not slots:
        return f"Ngày {date} tin {listing_id} đã kín lịch, không còn khung giờ trống. Hãy thử ngày khác."
    return f"Ngày {date} tin {listing_id} còn trống các khung giờ: {', '.join(slots)}"


def book_viewing(listing_id: str, date: str, slot: str, name: str) -> str:
    """
    Đặt lịch đi xem phòng. ĐÂY LÀ HÀNH ĐỘNG GHI, tạo lịch hẹn thật.

    Chỉ gọi khi người dùng đã nói rõ là muốn đặt lịch. Nếu người dùng mới chỉ hỏi
    tìm phòng thì phải hỏi xác nhận trước, không được tự ý đặt.

    Args:
        listing_id (str): Mã tin đăng (ví dụ: 'pr710261').
        date (str): Ngày xem, định dạng YYYY-MM-DD.
        slot (str): Khung giờ lấy từ check_viewing_slots (ví dụ: '14:00').
        name (str): Tên người đi xem phòng.

    Returns:
        str: Mã đặt lịch và thông tin xác nhận, hoặc thông báo lỗi nếu khung giờ đã bị đặt.
    """
    payload = {"listing_id": listing_id, "date": date, "slot": slot, "name": name}
    try:
        res = requests.post(f"{API_BASE_URL}/bookings", json=payload, timeout=TIMEOUT_SECONDS)
    except requests.RequestException:
        return CONNECTION_ERROR

    if not res.ok:
        return _error_from_response(res)

    booking = res.json()
    return (
        f"✅ Đặt lịch thành công! Mã đặt lịch: {booking['booking_ref']}\n"
        f"   Tin: {booking['listing_id']} - {booking['title']}\n"
        f"   Địa chỉ: {booking['address']}\n"
        f"   Thời gian: {booking['date']} lúc {booking['slot']}\n"
        f"   Người xem: {booking['name']}"
    )


def check_api_health() -> tuple[bool, str]:
    """Kiểm tra API còn sống không, dùng lúc app khởi động cho báo lỗi sớm và rõ ràng."""
    try:
        res = requests.get(f"{API_BASE_URL}/health", timeout=5)
        if res.ok:
            return True, f"{res.json().get('listings', '?')} tin đăng"
        return False, f"API trả về mã {res.status_code}"
    except requests.RequestException as e:
        return False, f"{type(e).__name__}"


# Danh sách các tool được đăng ký để Agent sử dụng
AVAILABLE_TOOLS = {
    "search_listings": search_listings,
    "get_listing_details": get_listing_details,
    "check_viewing_slots": check_viewing_slots,
    "book_viewing": book_viewing,
}

# 🛡️ Tool nào là hành động GHI (cần phanh an toàn trước khi cho gọi)
WRITE_TOOLS = {"book_viewing"}
