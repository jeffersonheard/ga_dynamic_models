"""
This module contains functions that may make your life easier, shortcuts for defining certain things in models
and APIs.  These are generally executed by the parser as the definition is parsed, as opposed to the names in 'utils',
which generally contains helper functions for creating parse-able entities.
"""

from tastypie.constants import ALL

def universal_filter(model):
    """Make APIs allow filtering on ALL fields.  This is dangerous for large tables."""
    return dict([(f.name, ALL) for f in model._meta.fields])