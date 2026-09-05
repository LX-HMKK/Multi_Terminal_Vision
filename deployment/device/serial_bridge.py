"""串口抽象层：把下位机串口封装成统一接口，支持真实串口与日志伪串口。

- RealSerial：基于 pyserial 的正式实现（Jetson Nano 上使用）。
- MockSerial：仅在日志打印发送内容，没有硬件时用来跑通整条指令链路。

用法：
    bridge = make_serial_bridge(mock=True)
    bridge.send_control("straight")   # 直接按语义发送
    bridge.send_bytes([2, 0x43])      # 或按裸字节发送
"""
from __future__ import annotations

import logging
from typing import Optional, Sequence

from .. import config


class SerialBridge:
    """串口统一接口。"""

    def __init__(self, logger: logging.Logger):
        self._logger = logger

    def send_bytes(self, data: Sequence[int]) -> None:
        raise NotImplementedError

    def send_control(self, name: str) -> None:
        """按语义名发送控制字节，name 不在 SIGNALS 则忽略。"""
        code = config.SIGNALS.get(name)
        if code is None:
            self._logger.warning("未知控制信号: %s", name)
            return
        self.send_bytes([code, config.CTRL_TRAIL])

    def close(self) -> None:
        raise NotImplementedError


class RealSerial(SerialBridge):
    """基于 pyserial 的真实串口。"""

    def __init__(self, port: str, baud: int, logger: logging.Logger):
        super().__init__(logger)
        import serial  # 延迟导入，mock 场景无需安装 pyserial

        try:
            self._ser = serial.Serial(port, baud, timeout=1)
            self._port = port
            self._logger.info("串口已打开 %s @ %d", port, baud)
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"无法打开串口 {port}: {exc}") from exc

    def send_bytes(self, data: Sequence[int]) -> None:
        payload = bytearray(data)
        self._ser.write(payload)
        self._logger.info("串口发送: %s", payload.hex())

    def close(self) -> None:
        try:
            self._ser.close()
            self._logger.info("串口已关闭 %s", self._port)
        except Exception as exc:  # noqa: BLE001
            self._logger.warning("关闭串口失败: %s", exc)


class MockSerial(SerialBridge):
    """日志伪串口：不接硬件，只打印发送内容。"""

    def __init__(self, logger: logging.Logger):
        super().__init__(logger)
        self._logger.info("串口已启用 MOCK 模式（仅日志，不发送）")

    def send_bytes(self, data: Sequence[int]) -> None:
        self._logger.info("[MOCK 串口] 发送: %s", bytearray(data).hex())

    def close(self) -> None:
        self._logger.info("[MOCK 串口] 关闭")


def make_serial_bridge(
    port: Optional[str] = None,
    baud: Optional[int] = None,
    logger: Optional[logging.Logger] = None,
) -> SerialBridge:
    """根据配置创建真实串口或伪串口。"""
    logger = logger or config.setup_logging()
    port = port or config.SERIAL_PORT
    baud = baud or config.BAUDRATE

    if port.lower() == "mock" or config.MOCK_SERIAL:
        return MockSerial(logger)
    return RealSerial(port, baud, logger)
