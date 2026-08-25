# core/proxy.py
import re
from mitmproxy import options
from mitmproxy.tools.dump import DumpMaster
from .addon import TextualMitmAddon


class ProxyManager:
    def __init__(self, app):
        self.app = app
        self.master = None

    def _get_regex_hosts(self, hosts_set: set) -> list[str]:
        return [f".*{re.escape(h)}.*" for h in hosts_set]

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
        opts = self._build_core_options(host, port)
        self.master = DumpMaster(opts, with_termlog=False, with_dumper=False)
        self.master.addons.add(TextualMitmAddon(self.app))

        # Addon options phải update sau khi master đã load addon
        self.master.options.update(
            anticache=self.app.opt_anticache,
            anticomp=self.app.opt_anticomp,
        )
        await self.master.run()

    def stop(self) -> None:
        if self.master:
            try:
                loop = self.master.event_loop
                if loop and not loop.is_closed():
                    loop.call_soon_threadsafe(self.master.shutdown)
            except Exception:
                pass
            finally:
                self.master = None

    def update_options(self, **kwargs) -> None:
        if self.master:
            self.master.options.update(**kwargs)

    @property
    def is_running(self) -> bool:
        return self.master is not None
