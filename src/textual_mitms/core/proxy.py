# core/proxy.py
from . import *
from .addon import TextualMitmAddon
from .utils import hosts_to_mitm_regex_list


class ProxyManager:
    def __init__(self, app):
        self.app = app
        self.master = None
        self._lock = threading.Lock()
        self._stop_requested = False

    def _get_regex_hosts(self, hosts_set: set) -> list[str]:
        # allow_hosts / ignore_hosts: sequence of regex, matched via
        # re.search(rex, host, re.IGNORECASE) trên hostname:port
        # (mitmproxy.addons.next_layer.NextLayer._ignore_connection)
        return hosts_to_mitm_regex_list(hosts_set)

    def _build_core_options(self, host: str, port: int) -> options.Options:
        allow_list = self._get_regex_hosts(self.app.allowed_hosts) if self.app.allowed_hosts else []
        ignore_list = self._get_regex_hosts(self.app.ignored_hosts) if self.app.ignored_hosts else []

        return options.Options(
            listen_host=host,
            listen_port=port,
            allow_hosts=allow_list,
            ignore_hosts=ignore_list,
            http2=self.app.opt_http2,
            http3=self.app.opt_http3,
            websocket=self.app.opt_websocket,
            ssl_insecure=self.app.opt_ssl_insecure,
        )

    async def start(self, host: str, port: int) -> None:
        """
        Chạy DumpMaster trên event loop hiện tại (worker thread gọi asyncio.run).

        DumpMaster/Master yêu cầu event loop đã có lúc __init__:
        event_loop = loop or asyncio.get_running_loop()
        (mitmproxy.tools.dump.DumpMaster, mitmproxy.master.Master)

        master.run() chỉ trả về sau khi should_exit được set (shutdown)
        rồi await done(). Không gán master = None trước thời điểm đó.
        """
        self._stop_requested = False
        opts = self._build_core_options(host, port)
        loop = asyncio.get_running_loop()

        with self._lock:
            if self.master is not None:
                return
            if self._stop_requested:
                return
            # DumpMaster.__init__(options, loop=None, with_termlog=True, with_dumper=True)
            self.master = DumpMaster(
                opts,
                loop=loop,
                with_termlog=False,
                with_dumper=False,
            )
            self.master.addons.add(TextualMitmAddon(self.app))
            # Addon options phải update sau khi master đã load addon
            self.master.options.update(
                anticache=self.app.opt_anticache,
                anticomp=self.app.opt_anticomp,
            )

        if self._stop_requested:
            # stop() được gọi trong lúc vừa tạo master
            self.master.shutdown()
        else:
            self.app.call_from_thread(self.app._on_proxy_started)

        try:
            await self.master.run()
        finally:
            with self._lock:
                self.master = None
            self._stop_requested = False

    def stop(self) -> None:
        """
        Yêu cầu tắt proxy. Master.shutdown() được docs ghi là thread-safe:
        event_loop.call_soon_threadsafe(self.should_exit.set)
        Không xóa self.master tại đây — run() sẽ xóa trong finally sau done().
        """
        self._stop_requested = True
        with self._lock:
            master = self.master
        if master is not None:
            master.shutdown()

    def update_options(self, **kwargs) -> None:
        with self._lock:
            master = self.master
        if master is not None:
            master.options.update(**kwargs)

    @property
    def is_running(self) -> bool:
        return self.master is not None
