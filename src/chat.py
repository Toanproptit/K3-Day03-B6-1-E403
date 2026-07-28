"""
💬 CLI CHAT — trò chuyện trực tiếp với ReAct Agent tìm & đặt lịch xem nhà trọ.

Chạy:
    Terminal 1:  uvicorn src.rental_api.server:app --port 8000
    Terminal 2:  python src/chat.py

Lệnh trong lúc chat:
    /gon     bật/tắt chế độ gọn (ẩn Thought - Action - Observation, chỉ xem câu trả lời)
    /bot     hỏi Chatbot baseline thay vì Agent, để so sánh hai bên
    /thoat   thoát
"""

import io
import os
import sys
from contextlib import redirect_stdout

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from app import run_baseline_chatbot, run_react_agent
from providers import get_llm_provider
from tools import check_api_health

BANNER = """
╭──────────────────────────────────────────────────────────╮
│  🏠  TRỢ LÝ TÌM & ĐẶT LỊCH XEM NHÀ TRỌ HÀ NỘI            │
╰──────────────────────────────────────────────────────────╯
Ví dụ câu hỏi:
  • Tìm phòng Cầu Giấy dưới 5 triệu
  • Phòng nào ở Thanh Xuân mới đăng trong 3 ngày qua?
  • Đặt lịch xem phòng pr710331 vào ngày mai, tên tôi là Toàn

Gõ /gon để ẩn bớt log, /bot để hỏi Chatbot thường, /thoat để thoát.
"""


def main() -> int:
    healthy, info = check_api_health()
    if not healthy:
        print(f"❌ Chưa kết nối được API cho thuê ({info}).")
        print("   Mở terminal khác và chạy: uvicorn src.rental_api.server:app --port 8000")
        return 1

    provider = get_llm_provider()
    model_name = getattr(provider, "model_name", "Mock")

    print(BANNER)
    print(f"🌐 API: OK ({info})    🔌 LLM: {provider.__class__.__name__} / {model_name}\n")

    concise = False

    while True:
        try:
            query = input("\n\033[1mBạn>\033[0m ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n👋 Tạm biệt!")
            return 0

        if not query:
            continue

        if query in ("/thoat", "/exit", "/quit"):
            print("👋 Tạm biệt!")
            return 0

        if query == "/gon":
            concise = not concise
            print(f"⚙️  Chế độ gọn: {'BẬT (chỉ hiện câu trả lời)' if concise else 'TẮT (hiện đủ trace)'}")
            continue

        use_baseline = query.startswith("/bot")
        if use_baseline:
            query = query[len("/bot"):].strip()
            if not query:
                print("⚠️  Dùng dạng: /bot <câu hỏi>")
                continue

        run = run_baseline_chatbot if use_baseline else run_react_agent

        try:
            if concise:
                # Nuốt toàn bộ log trung gian, chỉ giữ lại kết quả cuối
                buffer = io.StringIO()
                with redirect_stdout(buffer):
                    answer = run(query, provider)
                print(f"\n🤖 {answer}")
            else:
                run(query, provider)
        except KeyboardInterrupt:
            print("\n⏹️  Đã dừng câu hỏi này.")
        except Exception as e:
            print(f"\n❌ Lỗi khi xử lý: {type(e).__name__}: {e}")


if __name__ == "__main__":
    sys.exit(main())
