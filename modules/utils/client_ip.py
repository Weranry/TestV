"""客户端 IP 的唯一取法：限流计数范围与登录防撞库共用这一份，避免两处各写一套。

默认只认直连地址，不信任任何请求头：X-Forwarded-For 是客户端可自带的，拿它当身份
就等于把「限流」和「登录失败锁定」的钥匙交给攻击者（换一个伪造值即清零重试）。

挂在反向代理后面时，直连地址会退化成代理自己的 IP，于是所有设备共用一份限流额度，
而且攻击者刷满失败次数就能把该 IP 锁死——连管理员也一起被锁在门外。这种部署请把
config.TRUST_PROXY_HEADERS 打开，此时改取 X-Forwarded-For 的**最右一跳**：Nginx 的
$proxy_add_x_forwarded_for 与 Caddy 默认都是把真实来源追加在末尾，客户端伪造的值只会
留在左边，取最右才是本机代理写入的那一段（取最左是经典错误，等于完全放弃校验）。
多级代理串联时最右一跳是上一级代理的地址，这种拓扑需要按可信跳数另做处理，不在本实现内。
"""
import config


def client_ip(request):
    """请求来源 IP；取不到（测试用 ASGI 直调等）返回 'unknown' 而不是 None。"""
    if getattr(config, 'TRUST_PROXY_HEADERS', False):
        forwarded = request.headers.get('x-forwarded-for')
        if forwarded:
            hops = [h.strip() for h in forwarded.split(',') if h.strip()]
            if hops:
                return hops[-1]
    return request.client.host if request.client else 'unknown'