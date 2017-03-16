import configparser
import re


def generate_repo(name, url, **kwargs):
    repo = configparser.ConfigParser()
    repo.add_section(name)
    repo.set(name, 'baseurl', url)
    repo.set(name, 'name', name)
    for k, v in kwargs.viewitems():
        repo.set(name, k, str(v))
    return repo


def _filter_sections_by_pattern(config, pattern, negative=False):
    """
    Args:
        config(configparser.RawConfigParser) config to filter
        pattern(str) regex pattern
        negative(bool) if True remove all sections that don't match the pattern

    Returns:
        (generator) which generate the filtered sections

    """
    reg = re.compile(pattern)
    for section in config.sections():
        m = reg.match(section)
        if negative:
            m = not m
        if m:
            yield section


def filter_sections_by_pattern(config, pattern, negative=False):
    if not pattern:
        return config.sections()
    else:
        return _filter_sections_by_pattern(config, pattern, negative)


def strip_excludes_from_conf(config):
    return remove_option(config, 'exclude')


def remove_option(config, option, pattern=None, negative=False):
    """
    Args:
        config(configparser.RawConfigParser)
        option(str)
        pattern(str)
        negative(bool)

    Returns:
        The modified config

    """
    for section in filter_sections_by_pattern(config, pattern, negative):
        if config.has_option(section, option):
            config.remove_option(section, option)

    return config


def add_option_to_sections(
    config, option, value, pattern=None, negative=False
):
    for section in filter_sections_by_pattern(config, pattern, negative):
        config.set(section, option, value)


def collect_values(config, option, pattern=None, negative=False):
    s = set()
    for section in filter_sections_by_pattern(config, pattern, negative):
        if config.has_option(section, option):
            s.add(config.get(section, option))

    return s


def add_to_conf(base, other):
    """
    Add the sections from other to base.
    If section == main, merge base and other while giving precedence
    to options from other.

    If section != main, and section is in base, replace it with the new
    section from other.

    Args:
        other(configparser.RawConfigParser) new config
        base(configparser.RawConfigParser) base config

    Returns:
        (configparser.RawConfigParser) The modified config

    """
    for section in other.sections():
        if section != 'main' and base.has_section(section):
            base.remove_section(section)
        copy_section(other, base, section)

    return base


def copy_section(other, base, section):
    """
    Copy section from other to base.
    If section already exist in base, merge
    section from base and other while giving precedence to
    options from other.

    Args:
        other(configparser.RawConfigParser) new config
        base(configparser.RawConfigParser) base config
        section(str) which section to copy

    Returns:
        None

    """
    if not base.has_section(section):
        base.add_section(section)

    for option, value in other.items(section):
        base.set(section, option, value)


def remove_sections_by_pattern(config, pattern, negative=False):
    """
    Args:
        config(configparser.RawConfigParser) config to filter
        pattern(str) regex pattern
        negative(bool) if True remove all sections that don't match the pattern

    Returns:
        (configparser.RawConfigParser) The modified config

    """
    for section in filter_sections_by_pattern(config, pattern, negative):
        config.remove_section(section)

    return config
