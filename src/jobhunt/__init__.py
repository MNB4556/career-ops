"""job-hunt: a small, local-first job-application tracker."""

from jobhunt.models import STATUSES, Application, Posting

__all__ = ["STATUSES", "Application", "Posting"]
__version__ = "0.6.0"
