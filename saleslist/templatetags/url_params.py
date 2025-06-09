# saleslist/templatetags/url_params.py

from django import template
from urllib.parse import urlencode

register = template.Library()

@register.filter
def url_params(get_params, *args):
    query_dict = get_params.copy()

    for param in args:
        if "=" in param:
            key, value = param.split("=", 1)
            query_dict.pop(key, None)
            query_dict[key] = value

    return urlencode(query_dict)
