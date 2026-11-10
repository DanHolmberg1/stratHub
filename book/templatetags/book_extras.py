from django import template

from book.embeds import embed_src

register = template.Library()


@register.filter
def embed(url):
    return embed_src(url)


@register.simple_tag(takes_context=True)
def qs(context, **kwargs):
    """Current query string with some params replaced: {% qs side='CT' %}"""
    params = context["request"].GET.copy()
    for k, v in kwargs.items():
        if v in (None, ""):
            params.pop(k, None)
        else:
            params[k] = v
    return "?" + params.urlencode() if params else "?"
