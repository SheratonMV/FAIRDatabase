"""``solve_ivp`` for the study runners, one solve at a time per process.

Every runner integrates with ``solve_ivp(method="LSODA")``. scipy's LSODA
wraps the Fortran ODEPACK code, which keeps its working state in memory shared
by the whole process. When two solves run at once in different threads (the
Flask server handles each request in its own thread), they overwrite each
other's state. The run then fails with ``IntegratorConcurrencyError``, crashes
the process with a heap error, or returns wrong numbers without any error.

So all runners call ``solve_ivp`` from here, and one lock shared by all of them
makes the solves take turns. Solves in separate processes do not share this
state and are not affected.
"""
import threading

from scipy.integrate import solve_ivp as _scipy_solve_ivp

_lock = threading.Lock()


def solve_ivp(*args, **kwargs):
    """scipy's ``solve_ivp``, run while holding the process-wide solver lock."""
    with _lock:
        return _scipy_solve_ivp(*args, **kwargs)
