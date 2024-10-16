import logging
from logging import handlers


class sys_print_obj(object):
    def __init__(self):
        pass

    def info(self, str):
        print("(info) %s", str)

    def warning(self, str):
        print("(warning) %s", str)

    def debug(self, str):
        print("(debug) %s", str)

    def error(self, str):
        print("(error) %s", str)


class P_Logger(object):
    def __init__(self):
        self.logger = sys_print_obj()

    
class Logger(object):
    level_relations = {
        "debug": logging.DEBUG,
        "info": logging.INFO,
        "warning": logging.WARNING,
        "error": logging.ERROR,
        "crit": logging.CRITICAL,
    }  # 日志级别关系映射
    #%(pathname)s[line:%(lineno)d]
    def __init__(
        self,
        filename,
        level="info",
        when="D",
        backCount=3,
        fmt="%(asctime)s - %(levelname)s: %(message)s",
        console=True,
    ):
        self.logger = logging.getLogger("main")
        format_str = logging.Formatter(fmt)  # 设置日志格式
        self.logger.setLevel(self.level_relations.get(level))  # 设置日志级别
        self.console=console
        sh = logging.StreamHandler()  # 往屏幕上输出W
        sh.setFormatter(format_str)  # 设置屏幕上显示的格式
        th = handlers.TimedRotatingFileHandler(
            filename=filename, when=when, backupCount=backCount, encoding="utf-8"
        )  # 往文件里写入#指定间隔时间自动生成文件的处理器
        # 实例化TimedRotatingFileHandler
        # interval是时间间隔，backupCount是备份文件的个数，如果超过这个个数，就会自动删除，when是间隔的时间单位，单位有以下几种：
        # S 秒
        # M 分
        # H 小时、
        # D 天、
        # W 每星期（interval==0时代表星期一）
        # midnight 每天凌晨
        th.setFormatter(format_str)  # 设置文件里写入的格式
        self.logger.addHandler(sh)  # 把对象加到logger里
        if self.console:
            self.logger.addHandler(th)

    def getLogger(self):
        return self.logger
