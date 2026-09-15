"""Reserved integration boundary. No external posting is implemented in this MVP."""


def publish(*args, **kwargs):
    raise NotImplementedError("Fanvue publication is not configured; export approved content manually.")
