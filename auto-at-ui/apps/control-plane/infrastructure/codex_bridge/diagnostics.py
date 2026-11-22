"""Exception metadata without exception messages, file paths, or payload values."""

import errno


def exception_details(error: BaseException) -> dict:
    def describe(item):
        number = getattr(item, "errno", None)
        windows = getattr(item, "winerror", None)
        return {
            "error_type": type(item).__name__,
            "errno": number if isinstance(number, int) else None,
            "errno_name": errno.errorcode.get(number) if isinstance(number, int) else None,
            "winerror": windows if isinstance(windows, int) else None,
        }

    frames = []
    trace = error.__traceback__
    while trace is not None:
        module = trace.tb_frame.f_globals.get("__name__", "")
        if module.startswith(("infrastructure.", "application.", "agents.", "auto_at.")):
            frames.append({"module": module, "function": trace.tb_frame.f_code.co_name,
                           "line": trace.tb_lineno})
        trace = trace.tb_next
    chain, seen, cause = [], {id(error)}, error.__cause__ or error.__context__
    while cause is not None and id(cause) not in seen and len(chain) < 3:
        seen.add(id(cause))
        chain.append(describe(cause))
        cause = cause.__cause__ or cause.__context__
    return {**describe(error), "error_chain": chain, "code_locations": frames[-8:]}
