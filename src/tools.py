"""
🛠️ TOOL REGISTRY & SCHEMAS (Dành cho Role 2: Tool & Spec Engineer)
Nơi khai báo tất cả các "món đồ nghề" mà ReAct Agent có thể gọi.
"""

from datetime import date, time
import re
import unicodedata


def get_weather(location: str) -> str:
    """
    Tra cứu thời tiết hiện tại của một thành phố.

    Args:
        location (str): Tên thành phố (Ví dụ: 'Hà Nội', 'TP.HCM', 'Đà Nẵng')

    Returns:
        str: Thông tin thời tiết chi tiết
    """
    loc_lower = location.lower()
    if "hà nội" in loc_lower or "ha noi" in loc_lower:
        return "Thời tiết Hà Nội: 28°C, Nắng nhẹ, Độ ẩm 65%."
    elif "hồ chí minh" in loc_lower or "tp.hcm" in loc_lower or "hcm" in loc_lower:
        return "Thời tiết TP.HCM: 33°C, Nắng nóng, Có mây."
    elif "đà nẵng" in loc_lower or "da nang" in loc_lower:
        return "Thời tiết Đà Nẵng: 30°C, Gió nhẹ, Mát mẻ."
    else:
        return f"LỖI: Không tìm thấy dữ liệu thời tiết cho địa điểm '{location}'."


def search_flights(origin: str, destination: str) -> str:
    """
    Tra cứu chuyến bay giữa hai địa điểm.

    Args:
        origin (str): Nơi đi (Ví dụ: 'TP.HCM')
        destination (str): Nơi đến (Ví dụ: 'Hà Nội')

    Returns:
        str: Danh sách chuyến bay khả dụng và giá vé
    """
    return (
        f"Chuyến bay từ {origin} -> {destination} ngày mai:\n"
        f"1. VN123 (08:00) - Giá: 1,500,000 VNĐ (Còn vé)\n"
        f"2. VJ456 (14:30) - Giá: 1,200,000 VNĐ (Còn vé)"
    )


# Dữ liệu mẫu deterministic cho bài toán Trợ Lý Tìm & Đặt Lịch Xem Nhà Trọ / Căn Hộ
RENTAL_LISTINGS = [
    {
        "id": "NT001",
        "title": "Phòng trọ full nội thất gần Đại học Bách Khoa Hà Nội",
        "property_type": "phòng trọ",
        "location": "Hai Bà Trưng, Hà Nội",
        "address": "Ngõ Trần Đại Nghĩa, Hai Bà Trưng, Hà Nội",
        "nearby_landmarks": ["Đại học Bách Khoa Hà Nội", "Đại học Xây dựng", "Đại học Kinh tế Quốc dân"],
        "price": 3800000,
        "area_m2": 22,
        "bedrooms": 0,
        "amenities": ["điều hòa", "nóng lạnh", "wifi", "chỗ để xe"],
        "notes": "Phù hợp sinh viên, đi bộ 7 phút tới cổng trường.",
        "available_slots": {
            "2026-07-29": ["09:00", "14:00", "18:00"],
            "2026-07-30": ["10:00", "16:30"],
            "2026-07-31": ["19:00"],
        },
    },
    {
        "id": "NT002",
        "title": "Phòng trọ khép kín gần Bách Khoa, giá tiết kiệm",
        "property_type": "phòng trọ",
        "location": "Hai Bà Trưng, Hà Nội",
        "address": "Phố Tạ Quang Bửu, Hai Bà Trưng, Hà Nội",
        "nearby_landmarks": ["Đại học Bách Khoa Hà Nội"],
        "price": 3200000,
        "area_m2": 18,
        "bedrooms": 0,
        "amenities": ["wifi", "gác xép", "chỗ để xe"],
        "notes": "Giá tốt nhưng không có điều hòa.",
        "available_slots": {
            "2026-07-29": ["11:00"],
            "2026-07-31": ["15:00"],
        },
    },
    {
        "id": "CH001",
        "title": "Căn hộ 1 phòng ngủ yên tĩnh tại Cầu Giấy",
        "property_type": "căn hộ 1 phòng ngủ",
        "location": "Cầu Giấy, Hà Nội",
        "address": "Ngõ 165 Xuân Thủy, Cầu Giấy, Hà Nội",
        "nearby_landmarks": ["Công viên Cầu Giấy", "Đại học Quốc gia Hà Nội"],
        "price": 7500000,
        "area_m2": 35,
        "bedrooms": 1,
        "amenities": ["điều hòa", "máy giặt", "ban công", "thang máy", "bãi xe"],
        "notes": "Phù hợp ở 1-2 người, vào ở ngay.",
        "available_slots": {
            "2026-08-01": ["14:00", "16:00"],
            "2026-08-02": ["09:30"],
        },
    },
    {
        "id": "CH002",
        "title": "Căn hộ 1 phòng ngủ cao cấp gần Duy Tân",
        "property_type": "căn hộ 1 phòng ngủ",
        "location": "Cầu Giấy, Hà Nội",
        "address": "Phố Duy Tân, Cầu Giấy, Hà Nội",
        "nearby_landmarks": ["Tòa nhà Keangnam", "Duy Tân"],
        "price": 9200000,
        "area_m2": 40,
        "bedrooms": 1,
        "amenities": ["điều hòa", "máy giặt", "thang máy", "bảo vệ 24/7"],
        "notes": "Tiện nghi tốt nhưng vượt ngân sách 8 triệu.",
        "available_slots": {
            "2026-08-01": ["15:00"],
        },
    },
]


def _normalize_text(value: str) -> str:
    """Chuẩn hóa chuỗi để so khớp mềm hơn giữa các biến thể tiếng Việt."""
    if value is None:
        return ""
    text = unicodedata.normalize("NFD", str(value).strip().lower())
    text = "".join(char for char in text if unicodedata.category(char) != "Mn")
    text = text.replace("đ", "d")
    return re.sub(r"\s+", " ", text)


def _parse_budget(value) -> float:
    """Đọc ngân sách từ số hoặc chuỗi như '4 triệu', '8.000.000'."""
    if isinstance(value, (int, float)):
        return float(value)

    normalized = _normalize_text(str(value))
    compact = normalized.replace(" ", "")

    if not compact:
        raise ValueError("Ngân sách rỗng")

    compact = compact.replace("vnd", "").replace("vnđ", "").replace("dong", "")

    if "trieu" in compact:
        number_text = compact.replace("trieu", "").replace(",", ".")
        return float(number_text) * 1_000_000

    if compact.endswith("k"):
        return float(compact[:-1].replace(",", ".")) * 1_000

    digits_only = re.sub(r"[^0-9.]", "", compact)
    if digits_only.count(".") > 1:
        digits_only = digits_only.replace(".", "")

    if not digits_only:
        raise ValueError("Không đọc được ngân sách")

    return float(digits_only)


def _find_listing(listing_id: str):
    """Tìm tin đăng theo mã."""
    target = _normalize_text(listing_id)
    for listing in RENTAL_LISTINGS:
        if _normalize_text(listing["id"]) == target:
            return listing
    return None


def _format_currency(amount: float) -> str:
    """Định dạng giá VND dễ đọc."""
    return f"{int(amount):,} VNĐ/tháng".replace(",", ".")


def _get_searchable_text(listing: dict) -> str:
    """Gộp các trường để tìm kiếm nhẹ bằng substring."""
    pieces = [
        listing["title"],
        listing["property_type"],
        listing["location"],
        listing["address"],
        listing["notes"],
        " ".join(listing["nearby_landmarks"]),
        " ".join(listing["amenities"]),
    ]
    return _normalize_text(" ".join(pieces))


def _next_available_slot(listing: dict) -> str:
    """Lấy slot sớm nhất để hiển thị nhanh trong kết quả tìm kiếm."""
    slots = []
    for slot_date, slot_times in listing["available_slots"].items():
        for slot_time in slot_times:
            slots.append(f"{slot_date} {slot_time}")
    return min(slots) if slots else "Chưa có lịch trống"


def search_rentals(location: str, budget_max, property_type: str, amenities: str = "") -> str:
    """
    Tìm nhà trọ/căn hộ phù hợp theo khu vực, ngân sách, loại hình và tiện ích.

    Args:
        location (str): Khu vực, địa danh hoặc mốc gần đó (Ví dụ: 'Đại học Bách Khoa Hà Nội', 'Cầu Giấy')
        budget_max: Ngân sách tối đa mỗi tháng (Ví dụ: 4000000, '4 triệu')
        property_type (str): Loại hình thuê (Ví dụ: 'phòng trọ', 'căn hộ 1 phòng ngủ')
        amenities (str): Tiện ích mong muốn, phân tách bằng dấu phẩy nếu có nhiều mục

    Returns:
        str: Danh sách tin đăng phù hợp hoặc thông báo lỗi
    """
    try:
        budget_limit = _parse_budget(budget_max)
    except ValueError:
        return f"LỖI: Không đọc được ngân sách tối đa từ giá trị '{budget_max}'."

    location_query = _normalize_text(location)
    property_query = _normalize_text(property_type)
    amenity_terms = [
        term.strip() for term in _normalize_text(amenities).split(",") if term.strip()
    ]

    matches = []
    for listing in RENTAL_LISTINGS:
        searchable_text = _get_searchable_text(listing)

        if location_query and location_query not in searchable_text:
            continue
        if property_query and property_query not in searchable_text:
            continue
        if listing["price"] > budget_limit:
            continue
        listing_amenities = _normalize_text(" ".join(listing["amenities"]))
        if any(term not in listing_amenities for term in amenity_terms):
            continue
        if not listing["available_slots"]:
            continue

        matches.append(listing)

    if not matches:
        return (
            "LỖI: Không tìm thấy nhà trọ/căn hộ phù hợp với khu vực, ngân sách, "
            "loại hình và tiện ích đã cung cấp."
        )

    lines = [
        f"Tìm thấy {len(matches)} lựa chọn phù hợp cho khu vực '{location}' trong ngân sách tối đa {_format_currency(budget_limit)}:"
    ]
    for index, listing in enumerate(matches, start=1):
        lines.append(
            f"{index}. {listing['id']} - {listing['title']} | Giá: {_format_currency(listing['price'])} | "
            f"Diện tích: {listing['area_m2']}m² | Địa chỉ: {listing['address']} | "
            f"Tiện ích: {', '.join(listing['amenities'])} | Slot gần nhất: {_next_available_slot(listing)}"
        )
    lines.append("Dùng listing_id để gọi check_viewing_slots hoặc schedule_viewing nếu muốn đặt lịch xem nhà.")
    return "\n".join(lines)


def check_viewing_slots(listing_id: str, viewing_date: str) -> str:
    """
    Kiểm tra các khung giờ xem nhà còn trống cho một tin đăng.

    Args:
        listing_id (str): Mã tin đăng (Ví dụ: 'NT001', 'CH001')
        viewing_date (str): Ngày muốn xem nhà theo định dạng YYYY-MM-DD

    Returns:
        str: Danh sách khung giờ còn trống hoặc thông báo lỗi
    """
    listing = _find_listing(listing_id)
    if not listing:
        return f"LỖI: Không tìm thấy tin đăng có mã '{listing_id}'."

    try:
        normalized_date = date.fromisoformat(viewing_date).isoformat()
    except ValueError:
        return f"LỖI: Ngày xem nhà '{viewing_date}' không đúng định dạng YYYY-MM-DD."

    slots = listing["available_slots"].get(normalized_date, [])
    if not slots:
        return f"LỖI: Không còn lịch xem trống cho tin '{listing_id}' vào ngày {normalized_date}."

    return (
        f"Lịch xem còn trống cho {listing['id']} - {listing['title']} vào ngày {normalized_date}: "
        f"{', '.join(slots)}."
    )


def schedule_viewing(
    listing_id: str,
    viewing_date: str,
    viewing_time: str,
    customer_name: str = "Khách hàng",
    phone: str = "Chưa cung cấp",
) -> str:
    """
    Đặt lịch xem nhà cho một tin đăng nếu còn khung giờ trống.

    Args:
        listing_id (str): Mã tin đăng cần đặt lịch
        viewing_date (str): Ngày xem nhà theo định dạng YYYY-MM-DD
        viewing_time (str): Giờ xem nhà theo định dạng HH:MM
        customer_name (str): Tên người đi xem nhà
        phone (str): Số điện thoại liên hệ

    Returns:
        str: Xác nhận đặt lịch hoặc thông báo lỗi
    """
    listing = _find_listing(listing_id)
    if not listing:
        return f"LỖI: Không tìm thấy tin đăng có mã '{listing_id}'."

    if not str(customer_name).strip():
        return "LỖI: Vui lòng cung cấp tên người đặt lịch xem nhà."

    if not str(phone).strip():
        return "LỖI: Vui lòng cung cấp số điện thoại liên hệ."

    try:
        normalized_date = date.fromisoformat(viewing_date).isoformat()
    except ValueError:
        return f"LỖI: Ngày xem nhà '{viewing_date}' không đúng định dạng YYYY-MM-DD."

    try:
        normalized_time = time.fromisoformat(viewing_time).strftime("%H:%M")
    except ValueError:
        return f"LỖI: Giờ xem nhà '{viewing_time}' không đúng định dạng HH:MM."

    available_times = listing["available_slots"].get(normalized_date, [])
    if normalized_time not in available_times:
        return (
            f"LỖI: Khung giờ {normalized_date} {normalized_time} không khả dụng cho tin '{listing_id}'."
        )

    confirmation_code = (
        f"VIEW-{listing['id']}-{normalized_date.replace('-', '')}-{normalized_time.replace(':', '')}"
    )
    return (
        f"Đặt lịch xem nhà thành công. Mã xác nhận: {confirmation_code}. "
        f"Khách hàng: {customer_name.strip()}. SĐT: {phone.strip()}. "
        f"Tin đăng: {listing['title']} - {listing['address']}. "
        f"Thời gian hẹn: {normalized_date} lúc {normalized_time}."
    )


# Danh sách các tool được đăng ký để Agent sử dụng
AVAILABLE_TOOLS = {
    "get_weather": get_weather,
    "search_flights": search_flights,
    "search_rentals": search_rentals,
    "check_viewing_slots": check_viewing_slots,
    "schedule_viewing": schedule_viewing,
}


def _self_check():
    """Kiểm tra nhanh 2 case tool chính của bài lab."""
    result_case_2 = search_rentals("Đại học Bách Khoa Hà Nội", "4 triệu", "phòng trọ", "điều hòa")
    assert "NT001" in result_case_2, result_case_2

    result_case_3_search = search_rentals("Cầu Giấy", "8 triệu", "căn hộ 1 phòng ngủ")
    assert "CH001" in result_case_3_search, result_case_3_search

    result_case_3_slots = check_viewing_slots("CH001", "2026-08-01")
    assert "14:00" in result_case_3_slots, result_case_3_slots

    result_case_3_booking = schedule_viewing("CH001", "2026-08-01", "14:00", "Nguyễn Văn A", "0901234567")
    assert "VIEW-CH001-20260801-1400" in result_case_3_booking, result_case_3_booking


if __name__ == "__main__":
    _self_check()
    print("Self-check tools thành công.")
