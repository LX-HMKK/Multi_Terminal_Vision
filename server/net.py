"""运算端网络链路（帧外收发 + 指令分发）。

从原 vision_server 中拆出，只负责网络 I/O 与指令分发，不涉及检测/帧源：
    TCPSender         自动重连的 TCP 客户端（按行分帧，可选鉴权/收行回调）
    UDPSender         向指定地址发送 JPEG 帧
    HostCommandHandler 把上位机指令解析后更新模式并转发 nano
    TrackState         跟踪目标生命周期（领域对象，喂给上位机事件通道）
"""
from __future__ import annotations

import select
import socket
import threading
import time


class TCPSender:
    """自动重连的 TCP 客户端，向 nano / 上位机发送指令（按行分帧，**以 `\\n` 结尾**）。

    线程安全 + 不阻塞设计：
    - 只有后台 `_loop` 线程建立连接，`_sock` 一律在 `_lock` 下读写，杜绝并发 connect。
    - socket 设为**非阻塞**：读线程用 `select` 轮询（0.5s），写用 `select` 等写就绪（1s 上限）。
      因此空闲不会误判为断开、也不会有 3s 超时残留导致抖动；
      未连接/对方无响应时 `send()` 快速返回，不会阻塞主循环。
    - 可选 `recv_handler` 处理收到的完整行（例如上位机指令）；EOF 会 flush 尾部残留。
    """

    def __init__(self, host: str, port: int, logger, name: str,
                 recv_handler=None, auth_line: str | None = None):
        self._host, self._port, self._name = host, port, name
        self._logger = logger
        self._recv_handler = recv_handler
        self._auth_line = auth_line              # 连接成功后发送的鉴权行（可选）
        self._sock: socket.socket | None = None
        self._stop = False
        self._lock = threading.Lock()
        self._down_log_at = 0.0                 # 降频的连接失败日志

    # ---- 连接生命周期 ----
    def start(self) -> None:
        threading.Thread(target=self._loop, daemon=True).start()

    def _loop(self) -> None:
        while not self._stop:
            with self._lock:
                need_connect = self._sock is None
            if need_connect:
                s = self._open()
                if s is not None:
                    self._attach(s)
            time.sleep(1.0)

    def _open(self) -> socket.socket | None:
        try:
            s = socket.create_connection((self._host, self._port), timeout=3.0)
        except OSError as exc:
            if time.time() - self._down_log_at > 5.0:
                self._logger.info("[%s] 连接 %s:%d 失败: %s（持续重连）",
                                  self._name, self._host, self._port, exc)
                self._down_log_at = time.time()
            return None
        s.setblocking(False)                    # 关键：避免 connect 超时残留在已连接 socket 上
        return s

    def _attach(self, s: socket.socket) -> None:
        with self._lock:
            old = self._sock
            self._sock = s
        if old is not None:
            self._safe_close(old)
        self._logger.info("[%s] 连接成功 %s:%d", self._name, self._host, self._port)
        if self._auth_line:
            self.send(self._auth_line)          # 可选鉴权握手
        if self._recv_handler:
            threading.Thread(target=self._reader, args=(s,), daemon=True).start()

    def _reader(self, sock: socket.socket) -> None:
        buf = b""
        sock.setblocking(False)
        while not self._stop:
            try:
                r, _, _ = select.select([sock], [], [], 0.5)
            except OSError:
                break
            if not r:
                continue
            try:
                chunk = sock.recv(4096)
            except BlockingIOError:
                continue
            except OSError:
                break
            if not chunk:
                break
            buf += chunk
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                if line.strip():
                    self._recv_handler(line.decode().strip())
        if buf.strip():                          # EOF 尾部残留 flush
            self._recv_handler(buf.decode().strip())
        with self._lock:
            if self._sock is sock:
                self._sock = None
        self._safe_close(sock)
        self._logger.info("[%s] 连接断开，等待重连", self._name)

    def send(self, text: str) -> bool:
        """发送一行（自动补 `\\n`）。未连接返回 False；最多等 1s 写就绪，不阻塞主循环。"""
        with self._lock:
            s = self._sock
            if s is None:
                return False
        payload = (text + "\n").encode()
        try:
            _, w, _ = select.select([], [s], [], 1.0)
            if not w:
                return False
            s.sendall(payload)
            return True
        except (BlockingIOError, OSError):
            with self._lock:
                if self._sock is s:
                    self._sock = None
            self._safe_close(s)
            return False

    def _safe_close(self, s: socket.socket) -> None:
        try:
            s.close()
        except OSError:
            pass

    def close(self) -> None:
        self._stop = True
        with self._lock:
            s = self._sock
            self._sock = None
        if s is not None:
            self._safe_close(s)


class UDPSender:
    """向指定地址发送 JPEG 帧。"""

    def __init__(self, addr: tuple[str, int], logger):
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._addr = addr

    def send_frame(self, jpeg: bytes) -> None:
        self._sock.sendto(jpeg, self._addr)

    def close(self) -> None:
        self._sock.close()


class TrackState:
    """跟踪目标生命周期：新出现/消失目标生成事件。"""

    def __init__(self):
        self._active: dict[int, dict] = {}

    def diff(self, seen_ids: set[int]) -> tuple[list[int], list[int]]:
        """返回 (新出现id, 消失id)。"""
        new_ids = list(seen_ids - set(self._active))
        gone_ids = [tid for tid in self._active if tid not in seen_ids]
        self._active = {tid: {} for tid in seen_ids}
        return new_ids, gone_ids


class HostCommandHandler:
    """处理上位机发来的指令，更新模式并转发 nano。"""

    def __init__(self, mode_holder: dict, nano: TCPSender, logger):
        self._mode_holder = mode_holder
        self._nano = nano
        self._logger = logger

    def __call__(self, cmd: str) -> None:
        cmd = cmd.strip()
        if not cmd:
            return
        if cmd in ("0", "1", "2", "3"):
            mode = int(cmd)
            self._mode_holder["mode"] = mode
            self._logger.info("上位机指令：模式 -> %d", mode)
            self._nano.send(cmd)      # 转发模式给 nano
        elif cmd in ("w", "a", "s", "d", "f", "g"):
            self._logger.info("上位机指令：%s", cmd)
            self._nano.send(cmd)
        else:
            self._logger.info("上位机指令：%s（忽略未知）", cmd)
