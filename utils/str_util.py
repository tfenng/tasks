import re


def remove_prefix(text, prefix):
    return re.sub(r'^{0}'.format(re.escape(prefix)), '', text)


def remove_prefix_dir(text, prefix):
    if prefix is None:
        return text
    if len(prefix) == 0:
        return text
    if not prefix.endswith('/'):
        prefix = prefix + '/'
    return remove_prefix(text, prefix)


def bytes2human(n):
    # http://code.activestate.com/recipes/578019
    # >>> bytes2human(10000)
    # '9.8K'
    # >>> bytes2human(100001221)
    # '95.4M'
    symbols = ('K', 'M', 'G', 'T', 'P', 'E', 'Z', 'Y')
    prefix = {}
    for i, s in enumerate(symbols):
        prefix[s] = 1 << (i + 1) * 10
    for s in reversed(symbols):
        if n >= prefix[s]:
            value = float(n) / prefix[s]
            return '%.1f%s' % (value, s)
    return "%sB" % n
