# saleslist/templatetags/custom_filters.py

from django import template

register = template.Library()

@register.filter
def result_color_class(result):
    if result in ['追わない', '不通留守', '担当不在', '失注']:
        return 'btn-secondary'
    elif result in ['見込', '再コール']:
        return 'btn-success'
    elif result == 'アポ成立':
        return 'btn-warning'
    elif result == '受注':
        return 'btn-danger'
    return 'btn-outline-primary'

from django import template
register = template.Library()

@register.filter
def dictkey(d, key):
    return d.get(str(key))