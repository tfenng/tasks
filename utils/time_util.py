import datetime
import time


def dt2str(dt, dt_format="%Y-%m-%d %H:%M:%S"):
    if not isinstance(dt, datetime.datetime):
        raise TypeError("{} is not of datetime".format(dt))
    return dt.strftime(dt_format)


def str2dt(dt_str, dt_format="%Y-%m-%d %H:%M:%S"):
    return datetime.datetime.strptime(dt_str, dt_format)


def now():
    return datetime.datetime.now()


def ts():
    return int(time.time())


def dt2ts(dt):
    return time.mktime(dt.timetuple())


def ts2dt(ts):
    return datetime.datetime.fromtimestamp(ts)


def current_sec():
    return code_sec_12(now())


def code_sec_12(dt):
    return dt2str(dt, "%y%m%d%H%M%S")


def now_str():
    return dt2str(now())
