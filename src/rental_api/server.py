"""
🌐 FASTAPI SERVER — API cho thuê phòng trọ (dữ liệu tổng hợp từ crawl thật)

Chạy:
    uvicorn src.rental_api.server:app --port 8000

Các endpoint:
    GET  /health                     kiểm tra server sống và đã nạp bao nhiêu tin
    GET  /listings                   tìm tin theo quận / giá / diện tích / độ mới
    GET  /listings/{id}              chi tiết một tin đăng
    GET  /listings/{id}/slots        khung giờ xem còn trống trong một ngày
    POST /bookings                   đặt lịch xem phòng
"""

import sys

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

from . import store

# Đảm bảo in Tiếng Việt và Emoji không lỗi trên Windows Console (cp1252)
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

app = FastAPI(
    title="Rental Viewing API",
    description="API tra cứu phòng trọ Hà Nội và đặt lịch xem, dựng từ dữ liệu crawl phongtro123.com.",
    version="1.0.0",
)


@app.on_event("startup")
def _startup() -> None:
    loaded = store.load()
    print(f"✅ Đã nạp {loaded} tin đăng vào bộ nhớ.")


class BookingRequest(BaseModel):
    listing_id: str = Field(..., description="Mã tin đăng, ví dụ pr710261")
    date: str = Field(..., description="Ngày xem phòng, dạng YYYY-MM-DD")
    slot: str = Field(..., description="Khung giờ, ví dụ 14:00")
    name: str = Field(..., description="Tên người đi xem")


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "listings": store.count()}


@app.get("/listings")
def list_listings(
    district: str | None = Query(None, description="Tên quận, có dấu hoặc không dấu đều được"),
    max_price: int | None = Query(None, ge=0, description="Giá thuê tối đa (VNĐ/tháng)"),
    min_area: float | None = Query(None, ge=0, description="Diện tích tối thiểu (m2)"),
    max_days_old: int | None = Query(None, ge=0, description="Chỉ lấy tin đăng trong N ngày qua"),
    limit: int = Query(5, ge=1, le=20, description="Số kết quả trả về"),
) -> dict:
    results = store.search(
        district=district,
        max_price=max_price,
        min_area=min_area,
        max_days_old=max_days_old,
        limit=limit,
    )
    return {"count": len(results), "results": results}


@app.get("/listings/{listing_id}")
def get_listing(listing_id: str) -> dict:
    try:
        return store.get(listing_id)
    except store.ListingNotFound:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy tin đăng có mã '{listing_id}'.")


@app.get("/listings/{listing_id}/slots")
def get_slots(
    listing_id: str,
    date: str = Query(..., description="Ngày muốn xem phòng, dạng YYYY-MM-DD"),
) -> dict:
    try:
        slots = store.slots_for(listing_id, date)
    except store.ListingNotFound:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy tin đăng có mã '{listing_id}'.")
    except store.InvalidDate as e:
        raise HTTPException(status_code=422, detail=str(e))
    return {"listing_id": listing_id, "date": date, "slots": slots}


@app.post("/bookings", status_code=201)
def create_booking(payload: BookingRequest) -> dict:
    try:
        return store.create_booking(payload.listing_id, payload.date, payload.slot, payload.name)
    except store.ListingNotFound:
        raise HTTPException(
            status_code=404, detail=f"Không tìm thấy tin đăng có mã '{payload.listing_id}'."
        )
    except store.InvalidDate as e:
        raise HTTPException(status_code=422, detail=str(e))
    except store.SlotUnavailable as e:
        raise HTTPException(status_code=409, detail=str(e))
