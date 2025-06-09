from django import template

register = template.Library()

@register.filter
def url_params(current_params, *new_params):
    """
    現在のGETパラメータに新しいパラメータをマージしてURLクエリ文字列に変換する。
    例: current_params='a=1&b=2' と new_params=['b=3', 'c=4'] を渡すと 'a=1&b=3&c=4'
    """
    from urllib.parse import parse_qs, urlencode

    # 現在のクエリパラメータを辞書化
    param_dict = {k: v[-1] for k, v in parse_qs(current_params).items()}

    for param in new_params:
        if "=" in param:
            key, value = param.split("=", 1)
            param_dict[key] = value

    return urlencode(param_dict)
