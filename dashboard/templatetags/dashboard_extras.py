from django import template

register = template.Library()


@register.filter
def get_item(dictionary, key):
    """Return dictionary[key], or an empty string if not found."""
    return dictionary.get(key, "")
