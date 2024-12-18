"""Custom JSON encoding utilities"""
import json
from datetime import datetime

class DateTimeEncoder(json.JSONEncoder):
    """Custom JSON encoder that handles datetime objects"""
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)

def json_dumps(obj):
    """Helper function to dump JSON with datetime handling"""
    return json.dumps(obj, cls=DateTimeEncoder)