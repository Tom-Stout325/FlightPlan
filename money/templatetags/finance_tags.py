from django import template
from django.conf import settings
import base64
from datetime import date

register = template.Library()

@register.simple_tag
def inline_logo():
    # Replace this path with your actual image path in your media folder or static
    logo_path = settings.BASE_DIR / 'static' / 'images' / 'logo.png'
    
    try:
        with open(logo_path, 'rb') as image_file:
            encoded_image = base64.b64encode(image_file.read()).decode('utf-8')
            return f"data:image/png;base64,{encoded_image}"
    except FileNotFoundError:
        return ""  # Return an empty string if the image is not found


@register.filter
def get_by_id(queryset, value):
    try:
        return queryset.get(id=value)
    except:
        return ""


@register.filter
def get_item(dictionary, key):
    return dictionary.get(key)


@register.filter
def until(value, max_value):
    return range(value, max_value)


@register.filter
def to_int(value):
    return int(value)


@register.simple_tag
def month_choices():
    return [(i, date(2000, i, 1).strftime('%B')) for i in range(1, 13)]


@register.filter
def get_range(start_year, offset):
    """
    Usage: {% for y in 2022|get_range:3 %}
    Generates: [2022, 2023, 2024, 2025]
    """
    return [start_year + i for i in range(int(offset) + 1)]


@register.simple_tag
def query_transform(query, **kwargs):
    """
    Returns the URL-encoded querystring with updated parameters.
    Usage: {% query_transform request.GET sort='date' direction='desc' %}
    """
    query = query.copy()
    for key, value in kwargs.items():
        query[key] = value
    return query.urlencode()


@register.filter
def lookup(dictionary, key):
    return dictionary.get(key, 0)

@register.filter
def until(value, max_value):
    return range(value, max_value)



@register.filter
def mul(value, arg):
    """Multiply the value by the arg."""
    try:
        return float(value) * float(arg)
    except (ValueError, TypeError):
        return 0
