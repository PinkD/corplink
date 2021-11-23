import copy
import os
import ssl
import time
import urllib.request
import http.cookiejar

from config import *

user_agent = "CorpLink/2.0.5 (linux; Linux Test Linux; en)"

url_postfix = "?os=Linux&os_version=Test+Linux"

get_login_method_url = f"https://%s/api/lookup{url_postfix}"
send_code_url = f"https://%s/api/login/code/send{url_postfix}"
verify_url = f"https://%s/api/login/code/verify{url_postfix}"
list_vpn_url = f"https://%s/api/vpn/list{url_postfix}"
fa2_url = f"https://%s/api/mfa/code/verify{url_postfix}"

ping_url = f"https://%s:%d/vpn/ping{url_postfix}"
conn_url = f"https://%s:%d/vpn/conn{url_postfix}"
keep_alive_url = f"https://%s:%d/vpn/report{url_postfix}"


def build_cookie(domain, name, value) -> http.cookiejar.Cookie:
    t = int(time.time()) + 3600 * 24 * 30
    return http.cookiejar.Cookie(
        version=0,
        name=name, value=value,
        port=None, port_specified=False,
        domain=domain, domain_specified=False, domain_initial_dot=False,
        path="/", path_specified=False,
        secure=False,
        expires=t,
        discard=False,
        comment=None,
        comment_url=None,
        rest={}
    )


class Client:
    def __init__(self, server: str, device_id, device_name, conf_path="."):
        self._cookiejar = None
        self._server = server
        self._domain = server.split(":")[0]
        self._api_opener = self._build_opener(os.path.join(conf_path, "cookie.txt"), device_id, device_name, True)
        self._vpn_opener = self._build_opener(os.path.join(conf_path, "cookie.txt"), device_id, device_name)

    def _ok(self, resp) -> bool:
        return resp["code"] == 0

    def no_verify_ctx(self):
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return ctx

    def _build_opener(self, cookie_path, device_id, device_name,
                      load_csrf_token=False) -> urllib.request.OpenerDirector:
        if self._cookiejar is None:
            self._cookiejar = http.cookiejar.MozillaCookieJar(cookie_path)
            try:
                self._cookiejar.load()
            except FileNotFoundError:
                pass
            except Exception as e:
                raise e
            if len(self._cookiejar) == 0:
                self._cookiejar.set_cookie(build_cookie(self._domain, "device_id", device_id))
                self._cookiejar.set_cookie(build_cookie(self._domain, "device_name", device_name))
        handlers = []
        ctx = self.no_verify_ctx()
        handlers.append(urllib.request.HTTPSHandler(context=ctx))
        # for mitm debug
        # handlers.append(urllib.request.ProxyHandler({"https": "http://192.168.1.233:8001/"}))
        handlers.append(urllib.request.HTTPCookieProcessor(self._cookiejar))
        opener = urllib.request.build_opener(*handlers)
        opener.addheaders.clear()
        opener.addheaders.append(("User-Agent", user_agent))
        csrf_token = self._find_in_cookie("csrf-token")
        if load_csrf_token and len(csrf_token) != 0:
            opener.addheaders.append(("Csrf-Token", csrf_token))
        return opener

    def _open(self, url: str, data: typing.Optional[typing.Dict]):
        if "%s" in url:
            url = url % (self._server,)
        if data is None:
            req = urllib.request.Request(url)
        else:
            data = json.dumps(data).encode()
            req = urllib.request.Request(url, data, headers={"Content-Type": "application/json"})
        if self._server in url:
            resp = self._api_opener.open(req).read()
            self._cookiejar.save()
            return json.loads(resp)
        else:
            resp = self._vpn_opener.open(req).read()
            return json.loads(resp)

    def get_login_method(self, username):
        data = {
            "forget_password": False,
            "platform": "",
            "user_name": username
        }
        resp = self._open(get_login_method_url, data)
        print(resp)

    def request_email_verify_code(self, username):
        data = {
            "code_type": "email",
            "forget_password": False,
            "platform": "",
            "user_name": username
        }
        resp = self._open(send_code_url, data)
        if not self._ok(resp):
            print(f"Failed to request email code: {resp}")
            return False
        print("code has been sent to your email")

    def login(self, code) -> bool:
        data = {
            "code": code,
            "code_type": "email",
            "forget_password": False,
        }
        resp = self._open(verify_url, data)
        if not self._ok(resp):
            print(f"Failed to login: {resp}")
            return False
        csrf_token = self._find_in_cookie("csrf-token")
        if len(csrf_token) != 0:
            self._api_opener.addheaders.append(("Csrf-Token", csrf_token))

        return True

    def verify(self, code) -> bool:
        data = {
            "action": "vpn",
            "code": code,
            "code_type": "otp"
        }
        resp = self._open(fa2_url, data)
        if not self._ok(resp):
            print(f"Failed to login: {resp}")
            return False
        return True

    def list_vpn(self) -> list:
        resp = self._open(list_vpn_url, None)
        if not self._ok(resp):
            print(f"Failed to login: {resp}")
            return []
        """
        {
            "api_port": 8001,
            "en_name": "CN",
            "icon": "123",
            "id": 1,
            "ip": "1.2.3.4",
            "name": "中国",
            "protocol_mode": 2,
            "timeout": 5,
            "vpn_port": 8002
        }
        """
        vpn_list = []
        for item in resp["data"]:
            vpn_list.append({
                "ip": item["ip"],
                "api_port": item["api_port"],
                "vpn_port": item["vpn_port"]
            })
        return vpn_list

    def ping_vpn(self, ip, port) -> bool:
        resp = self._open(ping_url % (ip, port), None)
        if not self._ok(resp):
            print(f"Failed to ping {ip}:{port}: {resp}")
            return False

        cookies = self._cookiejar._cookies
        for k, v in cookies.items():
            if k != self._domain:
                continue
            v = copy.deepcopy(v)
            for cs in v.values():
                for k in cs:
                    cs[k].domain = ip
            cookies[ip] = v
            break
        self._cookiejar.save()
        return True

    def _find_in_cookie(self, key) -> str:
        for v in self._cookiejar._cookies.values():
            for cs in v.values():
                for k, v in cs.items():
                    if k == key:
                        return v.value
        return ""

    def _cookie_to_str(self, cookiejar) -> str:
        cookies = []
        for v in cookiejar._cookies.values():
            for cs in v.values():
                for k, v in cs.items():
                    cookies.append(f"{k}={v.value}")
        cookie = "; ".join(cookies)
        return cookie

    def fetch_peer_info(self, ip, port, your_key) -> dict:
        data = {"public_key": your_key}
        resp = self._open(conn_url % (ip, port), data)
        if not self._ok(resp):
            if resp["code"] == 3002:
                print(resp["message"])
                return {"2-fa": None}
            else:
                print(f"failed to get vpn info: {resp}")
                return {}
        return resp["data"]

    def report_vpn_status(self, ip, port, wg_ip, public_key):
        data = {
            "ip": wg_ip,
            "mode": "Split",
            "public_key": public_key,
            "type": "100"
        }
        resp = self._open(keep_alive_url % (ip, port), data)
        if not self._ok(resp):
            print(f"failed to report vpn status: {resp}")
            return {}
