from contextvars import copy_context


def context_submit(executor, function, *args):
    """Propagate the same request's bounded tool counter into nested worker pools."""
    return executor.submit(copy_context().run, function, *args)
