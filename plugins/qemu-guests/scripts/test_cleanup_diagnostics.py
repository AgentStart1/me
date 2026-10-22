"""Public cleanup diagnostics contain fixed categories, never exception text."""
from collections import Counter
from dataclasses import dataclass
import subprocess

from resource_ownership import Cancelled
from test_environment_owner import CleanupUncertain, EnvironmentCleanupError
from test_guest_transport import TransportCleanupError


def failure_categories(failures):
    categories = Counter()
    seen = set()

    def visit(error):
        if id(error) in seen:
            return
        seen.add(id(error))
        if isinstance(error, (EnvironmentCleanupError, TransportCleanupError)):
            for child in error.failures:
                visit(child)
        elif isinstance(error, (Cancelled, KeyboardInterrupt, SystemExit)):
            categories['interrupted'] += 1
        elif isinstance(error, (TimeoutError, subprocess.TimeoutExpired)):
            categories['timeout'] += 1
        elif isinstance(error, PermissionError):
            categories['permission'] += 1
        elif isinstance(error, OSError):
            categories['io'] += 1
        elif isinstance(error, CleanupUncertain):
            categories['unconfirmed'] += 1
        else:
            categories['operation'] += 1

    for error in failures:
        visit(error)
    return categories


@dataclass(frozen=True, slots=True)
class CleanupReport:
    categories: tuple
    cleanup_uncertain: bool
    lease_retained: bool


def cleanup_report(owner):
    return CleanupReport(tuple(sorted(failure_categories(owner.cleanup_failures).items())),
                         owner.cleanup_uncertain, owner.lease_retained)


def report_cleanup(owner, stream):
    """Report the owner's committed result; do not inspect arbitrary cause chains."""
    report = owner if isinstance(owner, CleanupReport) else cleanup_report(owner)
    if not report.categories and not report.cleanup_uncertain:
        return
    categories = dict(report.categories) or {'ownership': 1}
    summary = ', '.join(f'{name}={count}' for name, count in sorted(categories.items()))
    try:
        print('Test environment cleanup incomplete: ' + summary + '.', file=stream)
        if report.lease_retained:
            print('Guest test lease retained for recovery; confirm ownership and guest processes before manual recovery.',
                  file=stream)
        else:
            print('No guest test lease was acquired by this run; inspect owned host processes before retrying.',
                  file=stream)
    except (OSError, ValueError):
        # Closed/broken diagnostic output must not replace the cancellation code.
        pass
