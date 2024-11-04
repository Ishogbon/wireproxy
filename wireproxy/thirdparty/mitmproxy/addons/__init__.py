from wireproxy.thirdparty.mitmproxy.addons import core
from wireproxy.thirdparty.mitmproxy.addons import streambodies
from wireproxy.thirdparty.mitmproxy.addons import upstream_auth


def default_addons():
    return [
        core.Core(),
        streambodies.StreamBodies(),
        upstream_auth.UpstreamAuth(),
    ]
