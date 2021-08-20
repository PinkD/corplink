import json
import typing
from string import Template

STAT_NOT_LOGIN = 0
STAT_LOGIN = 1
STAT_VERIFY = 2
STAT_READY = 3

default_device_name = "linux"


class ConfManager:
    def __init__(self, path, auto_dump=True):
        self._conf_path = path
        self._conf = self.load_conf()
        self._auto = auto_dump

    def load_conf(self) -> dict:
        try:
            with open(self._conf_path) as f:
                content = f.read()
            return json.loads(content)
        except FileNotFoundError:
            return {}

    def dump_conf(self):
        with open(self._conf_path, "w") as f:
            f.write(json.dumps(self._conf))

    def __contains__(self, k):
        return k in self._conf

    def __setitem__(self, k, v):
        self._conf[k] = v
        if self._auto:
            self.dump_conf()

    def __getitem__(self, k):
        try:
            return self._conf[k]
        except KeyError as e:
            if k == "state":
                return STAT_NOT_LOGIN
            else:
                raise e


class WireguardConfig:
    def __init__(self,
                 ip: str,
                 private_key: str,
                 public_key: str,
                 peer_key: str,
                 peer_ip: str,
                 mtu: int,
                 route: typing.List[typing.AnyStr],
                 template=None):
        self.ip = ip
        self.private_key = private_key
        self.public_key = public_key
        self.peer_key = peer_key
        self.peer_ip = peer_ip
        self.mtu = mtu
        self.route = route
        self._template = template
        if template is None:
            with open("template.conf") as f:
                self._template = Template(f.read())

    def __str__(self):
        # use copy to avoid changing self.__dict__
        data = self.__dict__.copy()
        data["route"] = ", ".join(data["route"])
        return self._template.substitute(data)
