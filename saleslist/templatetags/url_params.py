# saleslist/templatetags/url_params.py
from django import template
from urllib.parse import parse_qs, urlencode

register = template.Library()

@register.simple_tag
def url_params(request_get, **kwargs):
    """
    現在のGETパラメータに任意のキーを上書き・追加してURLクエリ文字列を返す。
    例: {% url_params request.GET sort='name' order='desc' %}
    """
    param_dict = {k: v[-1] for k, v in parse_qs(request_get.urlencode()).items()}

    for key, value in kwargs.items():
        param_dict[key] = value

    return urlencode(param_dict)
