"""
🗄️ KHO DỮ LIỆU TRONG BỘ NHỚ (tìm kiếm / lịch xem / đặt lịch)

Dữ liệu crawl chỉ có thông tin tin đăng, KHÔNG có lịch xem phòng.
Vì vậy khung giờ xem được sinh tổng hợp (synthetic) nhưng theo cách tất định:
cùng một mã tin + cùng một ngày luôn cho ra đúng bộ khung giờ đó, để trace log
của cả nhóm tái lập được y hệt khi chạy lại trên máy khác.
"""

import random
from datetime import date as date_cls
from datetime import datetime, timedelta

from . import normalize

# Các khung giờ chủ nhà thường cho xem phòng
SLOT_POOL = ["09:00", "10:30", "14:00", "15:30", "17:00"]

# Chỉ cho đặt lịch trong vòng 30 ngày tới
MAX_BOOKING_DAYS_AHEAD = 30


class ListingNotFound(Exception):
    """Không tìm thấy mã tin đăng."""


class InvalidDate(Exception):
    """Ngày không hợp lệ (sai định dạng, quá khứ, hoặc quá xa)."""


class SlotUnavailable(Exception):
    """Khung giờ không tồn tại hoặc đã có người đặt."""


_LISTINGS: list[dict] = []
_BY_ID: dict[str, dict] = {}
_BOOKINGS: dict[tuple[str, str, str], dict] = {}


def load(csv_path: str | None = None) -> int:
    """Nạp dữ liệu từ CSV vào bộ nhớ. Gọi một lần lúc server khởi động."""
    global _LISTINGS, _BY_ID
    _LISTINGS = normalize.load_listings(csv_path or normalize.CSV_PATH)
    _BY_ID = {item["id"]: item for item in _LISTINGS}
    return len(_LISTINGS)


def count() -> int:
    return len(_LISTINGS)


def search(
    district: str | None = None,
    max_price: int | None = None,
    min_area: float | None = None,
    max_days_old: int | None = None,
    limit: int = 5,
) -> list[dict]:
    """
    Lọc tin đăng theo quận, giá trần, diện tích tối thiểu và độ mới của tin.

    Quận so khớp không phân biệt dấu: 'Cầu Giấy', 'cau giay', 'CAU GIAY' đều khớp.
    Tin 'Thỏa thuận' (price_vnd = None) bị loại khi có max_price, vì không thể
    khẳng định nó nằm dưới ngưỡng giá người dùng yêu cầu.

    Kết quả sắp xếp tin mới nhất lên trước.
    """
    results = _LISTINGS

    if district:
        key = normalize.district_key(district)
        if key:
            results = [x for x in results if key in x["district_key"]]

    if max_price is not None:
        results = [x for x in results if x["price_vnd"] is not None and x["price_vnd"] <= max_price]

    if min_area is not None:
        results = [x for x in results if x["area_m2"] >= min_area]

    if max_days_old is not None:
        results = [x for x in results if x["days_old"] is not None and x["days_old"] <= max_days_old]

    # Tin mới nhất lên đầu; tin không rõ ngày đăng xuống cuối
    results = sorted(results, key=lambda x: (x["days_old"] is None, x["days_old"] or 0))
    return results[:limit]


def get(listing_id: str) -> dict:
    """Lấy chi tiết một tin đăng, ném ListingNotFound nếu mã không tồn tại."""
    item = _BY_ID.get(listing_id.strip())
    if item is None:
        raise ListingNotFound(listing_id)
    return item


def parse_and_validate_date(raw: str) -> date_cls:
    """
    Kiểm tra ngày xem phòng: đúng định dạng YYYY-MM-DD, không ở quá khứ,
    không quá 30 ngày tới. Cuối tuần vẫn hợp lệ vì đó là lúc người ta hay đi xem.
    """
    try:
        parsed = datetime.strptime(raw.strip(), "%Y-%m-%d").date()
    except ValueError:
        raise InvalidDate(f"Ngày '{raw}' sai định dạng, cần dạng YYYY-MM-DD (ví dụ 2026-07-29).")

    today = date_cls.today()
    if parsed < today:
        raise InvalidDate(f"Ngày {parsed.isoformat()} đã ở quá khứ, không đặt lịch xem được.")
    if parsed > today + timedelta(days=MAX_BOOKING_DAYS_AHEAD):
        raise InvalidDate(
            f"Ngày {parsed.isoformat()} quá xa, chỉ đặt lịch trong {MAX_BOOKING_DAYS_AHEAD} ngày tới."
        )
    return parsed


def slots_for(listing_id: str, raw_date: str) -> list[str]:
    """
    Sinh khung giờ xem phòng một cách tất định từ mã tin + ngày.

    Dữ liệu crawl không có lịch thật, nên đây là dữ liệu tổng hợp. Dùng seed cố
    định để cùng đầu vào luôn ra cùng kết quả — trace log nhờ vậy tái lập được.
    """
    item = get(listing_id)
    day = parse_and_validate_date(raw_date)

    rng = random.Random(f"{item['id']}:{day.isoformat()}")
    chosen = sorted(rng.sample(SLOT_POOL, rng.randint(2, 4)))

    taken = {slot for (lid, d, slot) in _BOOKINGS if lid == item["id"] and d == day.isoformat()}
    return [s for s in chosen if s not in taken]


def create_booking(listing_id: str, raw_date: str, slot: str, name: str) -> dict:
    """
    Đặt lịch xem phòng. Ném SlotUnavailable nếu khung giờ không có hoặc đã bị đặt.
    Lịch chỉ lưu trong bộ nhớ, khởi động lại server là mất.
    """
    item = get(listing_id)
    day = parse_and_validate_date(raw_date)
    slot = slot.strip()

    available = slots_for(listing_id, raw_date)
    if slot not in available:
        raise SlotUnavailable(
            f"Khung giờ {slot} không đặt được. Còn trống: {', '.join(available) or 'không còn khung nào'}."
        )

    key = (item["id"], day.isoformat(), slot)
    rng = random.Random(f"booking:{key}")
    record = {
        "booking_ref": f"BK-{rng.randint(1000, 9999)}",
        "listing_id": item["id"],
        "title": item["title"],
        "address": item["address"],
        "date": day.isoformat(),
        "slot": slot,
        "name": name.strip(),
    }
    _BOOKINGS[key] = record
    return record


def reset_bookings() -> None:
    """Xoá toàn bộ lịch đã đặt (dùng khi chạy lại bộ test cho sạch)."""
    _BOOKINGS.clear()
