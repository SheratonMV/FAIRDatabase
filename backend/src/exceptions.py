class GenericExceptionHandler(Exception):
    """
    Custom exception class for handling application-level errors in a consistent format.
    """

    status_code = 400

    def __init__(self, message, status_code=None, payload=None, redirect_to=None):
        super().__init__()
        self.message = message
        self.status_code = status_code or self.status_code
        self.payload = payload
        self.redirect_to = redirect_to

    def to_dict(self):
        rv = dict(self.payload or {})
        rv["message"] = self.message
        return rv
