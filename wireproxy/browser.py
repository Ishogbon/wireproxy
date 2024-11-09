from typing import Any, Dict

from wireproxy import backend, utils
from wireproxy.inspect import InspectRequestsMixin


class BrowserCommonMixin:
    """Attributes common to all Browser types."""

    def _setup_backend(self, wireproxy_options: Dict[str, Any]) -> Dict[str, Any]:
        """Create the backend proxy server and return its configuration
        in a dictionary.
        """
        self.backend = backend.create(
            addr=wireproxy_options.pop("addr", "127.0.0.1"),
            port=wireproxy_options.get("port", 0),
            options=wireproxy_options,
        )

        addr, port = utils.urlsafe_address(self.backend.address())

        config = {
            "proxy": {
                "proxyType": "manual",
                "httpProxy": "{}:{}".format(addr, port),
                "sslProxy": "{}:{}".format(addr, port),
            }
        }

        if "exclude_hosts" in wireproxy_options:
            # Only pass noProxy when we have a value to pass
            config["proxy"]["noProxy"] = wireproxy_options["exclude_hosts"]

        config["acceptInsecureCerts"] = True

        return config

    def quit(self):
        """Shutdown Wire Proxy"""
        self.backend.shutdown()

    @property
    def proxy(self) -> Dict[str, Any]:
        """Get the proxy configuration for the driver."""

        conf = {}
        mode = getattr(self.backend.master.options, "mode")

        if mode and mode.startswith("upstream"):
            upstream = mode.split("upstream:")[1]
            scheme, *rest = upstream.split("://")

            auth = getattr(self.backend.master.options, "upstream_auth")

            if auth:
                conf[scheme] = f"{scheme}://{auth}@{rest[0]}"
            else:
                conf[scheme] = f"{scheme}://{rest[0]}"

        no_proxy = getattr(self.backend.master.options, "no_proxy")

        if no_proxy:
            conf["no_proxy"] = ",".join(no_proxy)

        custom_auth = getattr(self.backend.master.options, "upstream_custom_auth")

        if custom_auth:
            conf["custom_authorization"] = custom_auth

        return conf

    @proxy.setter
    def proxy(self, proxy_conf: Dict[str, Any]):
        """Set the proxy configuration for the driver.

        The configuration should be a dictionary:

        webdriver.proxy = {
            'https': 'https://user:pass@server:port',
            'no_proxy': 'localhost,127.0.0.1',
        }

        Args:
            proxy_conf: The proxy configuration.
        """
        options = self.backend.master.options

        if proxy_conf:
            options.update(
                **utils.build_proxy_args(
                    utils.get_upstream_proxy({"proxy": proxy_conf})
                )
            )
        else:
            options.update(
                **{
                    utils.MITM_MODE: options.default(utils.MITM_MODE),
                    utils.MITM_UPSTREAM_AUTH: options.default(utils.MITM_UPSTREAM_AUTH),
                    utils.MITM_UPSTREAM_CUSTOM_AUTH: options.default(
                        utils.MITM_UPSTREAM_CUSTOM_AUTH
                    ),
                    utils.MITM_NO_PROXY: options.default(utils.MITM_NO_PROXY),
                }
            )


class ChromeProxy(InspectRequestsMixin, BrowserCommonMixin):
    """Extend the Chrome webdriver to provide additional methods for inspecting requests."""

    def __init__(self):
        """
        Initialise a new proxy instance
        """

        # Prevent Chrome from bypassing the Wire Proxy
        # for localhost addresses.
        proxy_options = {}
        # proxy_options.add_argument("--proxy-bypass-list=<-loopback>")

        config = self._setup_backend(proxy_options)

        if proxy_options.get("auto_config", True):
            for key, value in config.items():
                proxy_options[key] = value
        self.proxy_options = proxy_options
