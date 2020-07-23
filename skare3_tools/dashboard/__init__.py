from jinja2 import Environment, PackageLoader, select_autoescape

env = Environment(
    loader=PackageLoader('skare3_tools.dashboard', 'templates'),
    autoescape=select_autoescape(['html', 'xml'])
)

def get_template(*args, **kwargs):
    return env.get_template(*args, **kwargs)