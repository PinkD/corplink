# corplink wireguard config generator

[飞连](https://www.volcengine.com/product/vecorplink) 配置生成器

## 原理

飞连基于 [wg-go](https://github.com/WireGuard/wireguard-go) 魔改了配置方式

猜测是：

- 动态管理的 peer
- 客户端通过验证后，使用 public key 来请求连接，然后服务端就将客户端的 key 加到 peer 库里，然后将配置返回给客户端
    - wg 是支持同一个接口上连多个 peer ，所以这样是 OK 的

因此，我们只需要生成 wg 的 key ，然后去找服务端拿配置，然后写到 wg 配置里，启动 wg 即可

## 使用指南

wg key 生成：

```shell
# gen private key
wg genkey | tee /tmp/private_key
# gen public key
wg pubkey < /tmp/private_key
# clean
rm /tmp/private_key
```

config.json

```json
{
  "username": "your_name",
  "public_key": "your_public_key",
  "private_key": "your_private_key",
  "server": "test.com:10443",
  "conf_file": "corplink.conf"
}
```

运行脚本，登录，验证，就会生成 wg 的配置文件  
然后复制到 `/etc/wireguard/` 下然后 `systemctl start wg-quic@corplink.service` 即可

> 注：如果登录信息出错，请清空 `cookie.txt` 和 `config.json` 中的 `state` 字段然后重新登录