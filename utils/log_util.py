import logging
import os
import sys

from loguru import logger


class InterceptHandler(logging.Handler):
    def emit(self, record):
        logger_opt = log().opt(depth=6, exception=record.exc_info)
        logger_opt.log(record.levelname, record.getMessage())


logging.basicConfig(handlers=[InterceptHandler()], level='INFO')
logger.remove()
fmt = "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level>" \
      "| <blue>{extra[component]}</blue> " \
      "| <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>"
logger.add(sys.stdout, colorize=True, format=fmt)


def set_component(s: str):
    os.environ["__EXEC_COMPONENT__"] = s


def show_pid(show: bool):
    os.environ["__EXEC_COMPONENT_SHOW_PID__"] = 'YES' if show else 'NO'


def log(s: str = None):
    if s is None:
        if os.environ.get("__EXEC_COMPONENT__"):
            if os.environ.get("__EXEC_COMPONENT_SHOW_PID__") == "YES":
                return logger.bind(component=f'{os.environ.get("__EXEC_COMPONENT__")}:pid-{os.getpid()}')
            else:
                return logger.bind(component=os.environ.get("__EXEC_COMPONENT__"))
        return logger.bind(component='DEFAULT')
    else:
        return logger.bind(component=s)
