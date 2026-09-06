import os
import struct
import zlib
from datetime import datetime


class QrCaptureService:
    """
    收银台支付二维码截图服务（C3 定稿）。
    真实实现：Playwright 定位收银台二维码元素 → 截图保存本地。
    当前阶段（Mock）：纯 Python 生成一张占位二维码风格 PNG，保存到 memory/qr/。
    """

    def __init__(self, qr_dir: str = ""):
        if not qr_dir:
            project_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            qr_dir = os.path.join(project_dir, "memory", "qr")
        self.qr_dir = qr_dir
        os.makedirs(self.qr_dir, exist_ok=True)

    async def capture(self, page=None, selector: str = "", order_no: str = "demo") -> str:
        if page is not None:
            # 真实模式：截图元素（携程收银台二维码）
            path = os.path.join(self.qr_dir, f"qr_{order_no}_{datetime.now().strftime('%H%M%S')}.png")
            await page.locator(selector).screenshot(path=path)
            return path
        return self._mock_qr(order_no)

    def _mock_qr(self, order_no: str) -> str:
        """生成占位二维码 PNG（模拟 QrCapture 产物）。"""
        path = os.path.join(self.qr_dir, f"qr_{order_no}_{datetime.now().strftime('%H%M%S')}.png")
        size = 128
        pixels = bytearray()
        seed = sum(ord(c) for c in order_no)
        for y in range(size):
            row = bytearray()
            for x in range(size):
                # 简单伪随机块 + 三个定位角
                in_finder = self._in_finder(x, y, size)
                if in_finder:
                    v = 0
                else:
                    v = 255 if ((x * 7 + y * 13 + seed) % 3) else 0
                row.extend((v, v, v, 255))
            pixels.extend(row)
        raw = b"".join(
            b"\x00" + bytes(pixels[y * size * 4:(y + 1) * size * 4])
            for y in range(size)
        )

        def chunk(tag: bytes, data: bytes) -> bytes:
            c = struct.pack(">I", len(data)) + tag + data
            return c + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

        ihdr = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)
        png = (
            b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", zlib.compress(raw))
            + chunk(b"IEND", b"")
        )
        with open(path, "wb") as f:
            f.write(png)
        return path

    @staticmethod
    def _in_finder(x: int, y: int, size: int) -> bool:
        """三个定位角：左上/右上/左下"""
        for ox, oy in ((0, 0), (size - 21, 0), (0, size - 21)):
            if ox <= x < ox + 21 and oy <= y < oy + 21:
                rx, ry = x - ox, y - oy
                if 0 <= rx < 7 and 0 <= ry < 7:
                    return True
                if 7 <= rx < 14 and 7 <= ry < 14:
                    return 7 <= rx < 14 and 7 <= ry < 14
                if 14 <= rx < 21 and 14 <= ry < 21:
                    return True
        return False
