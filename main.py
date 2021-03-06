import os
import signal
import sys
import time

import pyotp

import utils
from config import *
from request import Client


class CorpLink:
    def __init__(self, conf_path="."):
        self._conf = ConfManager(os.path.join(conf_path, "config.json"))
        self._conf_file = "corplink.conf"
        try:
            self._username = self._conf["username"]
            self._public_key = self._conf["public_key"]
            self._private_key = self._conf["private_key"]

            if "totp" in self._conf:
                self._otp = pyotp.TOTP(self._conf["totp"])

            self._device_name = default_device_name
            self._password = ""
            if "password" in self._conf:
                self._password = self._conf["password"]
            if "device_name" in self._conf:
                self._device_name = self._conf["device_name"]
            self._device_id = utils.device_id_from_name(self._device_name)
            if "device_id" in self._conf:
                self._device_id = self._conf["device_id"]

            self._client = Client(self._conf["server"], self._device_id, self._device_name, conf_path)

            if "conf_file" in self._conf:
                self._conf_file = self._conf["conf_file"]
        except KeyError as e:
            print(f"require conf in config.json: {e}")
            exit(1)

    @property
    def state(self):
        return self._conf["state"]

    @state.setter
    def state(self, v):
        self._conf["state"] = v

    def need_login(self) -> bool:
        return self.state == STAT_NOT_LOGIN

    def need_verify(self) -> bool:
        return self.state == STAT_LOGIN

    def login(self) -> bool:
        auth = self._client.get_login_method(self._username)
        if len(auth) == 0:
            print("No available auth")
            return False
        if "password" in auth:
            if len(self._password) != 0:
                self._otp = self._client.login_with_password(self._username, self._password)
                self.state = STAT_LOGIN
                self._conf["totp"] = self._otp.secret
                return True
            else:
                print("No password provided, try to use another method")
        if "email" in auth:
            self._client.request_email_verify_code(self._username)
            code = input("code from your email:")
            self._otp = self._client.login_with_code(code)
            self._conf["totp"] = self._otp.secret
            self.state = STAT_LOGIN
            return True
        return False

    def verify(self) -> bool:
        ok = self._client.verify(self._otp.now())
        if ok:
            print("2 fa verify success")
            self.state = STAT_VERIFY
        return ok

    def generate_wg_conf_and_keep_alive(self) -> typing.Optional[WireguardConfig]:
        vpn_list = self._client.list_vpn()
        if vpn_list is None:
            self.state = STAT_NOT_LOGIN
            return
        if len(vpn_list) == 0:
            print("No available vpn")
            return
        print(f"Found vpn: {json.dumps(vpn_list, indent=2)}")
        vpn = None
        for v in vpn_list:
            if self._client.ping_vpn(v["ip"], v["api_port"]):
                vpn = v
                break
        if vpn is None:
            print("No available vpn")

        ip, port = vpn["ip"], vpn["api_port"]

        private_key = self._private_key
        public_key = self._public_key
        info = self._client.fetch_peer_info(ip, port, public_key, self._otp.now())
        if len(info) == 0:
            return
        if "2-fa" in info:
            # need to verify 2-fa
            self._conf["state"] = STAT_LOGIN
            return

        self.state = STAT_READY
        wg_ip = info["ip"]
        conf = WireguardConfig(
            ip=f'{wg_ip}/{info["ip_mask"]}',
            private_key=private_key,
            public_key=public_key,
            peer_key=info["public_key"],
            peer_ip=f'{vpn["ip"]}:{vpn["vpn_port"]}',
            mtu=info["setting"]["vpn_mtu"],
            route=info["setting"]["vpn_route_split"],
        )
        print(conf)
        with open(self._conf_file, "w") as f:
            f.write(str(conf))

        def signal_handler(sig, frame):
            print('Disconnecting...')
            self._client.disconnect_vpn(ip, port, wg_ip, public_key)
            sys.exit(0)

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        while True:
            try:
                print("keep connection alive")
                self._client.report_vpn_status(ip, port, wg_ip, public_key)
                time.sleep(60)
            except Exception as e:
                raise e


if __name__ == '__main__':
    corp_link = CorpLink()
    if corp_link.need_login():
        # TODO: generate private and public key
        #       because if other client terminates this session, the public key will be invalid
        if not corp_link.login():
            exit(1)

    # if corp_link.need_verify():
    #     if not corp_link.verify():
    #         exit(1)

    corp_link.generate_wg_conf_and_keep_alive()
