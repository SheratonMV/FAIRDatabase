class GenericExceptionHandler(Exception):
    """
    Custom exception class for handling application-level errors in a consistent format.
    ---
    tags:
      - error-handling
    parameters:
      - name: message
        type: string
        description: Human-readable error message to be returned in the response.
      - name: status_code
        type: integer
        default: 400
        description: HTTP status code to return with the error.
      - name: payload
        type: object
        description: Optional additional data to include in the error response.
    returns:
      type: object
      description: A dictionary representation of the error for JSON serialization.
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
