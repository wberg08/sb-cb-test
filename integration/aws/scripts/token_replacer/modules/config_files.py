#!/usr/bin/env python

from __future__ import absolute_import
import logging
import yaml
import yamlordereddictloader
import re
import os

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def load_build_configs(filename):
    # Opens the build configuration YAML and Parses into dictionary.
    with open(filename, 'r') as stream:
        try:
            cfg = (yaml.load(stream, Loader=yamlordereddictloader.Loader))  # pylint: disable=yaml_load
        except yaml.YAMLError as exc:
            logger.error(exc)
        return cfg


def token_replacer_factory(spelling_dict):
    def replacer(match):
        word = match.group()
        return spelling_dict.get(word, word)

    return replacer


def get_transform_configs(build_config, build_type, location, suffix, project_name, account_name,
                          env_name=None, env_num=None):
    logger.info('build type: %s', build_type)
    config_files = build_config['config'][build_type]['include']
    subst_list = ['[project_name]', '[account_name]']
    input_list = [project_name, account_name]

    if bool(env_name) != bool(env_num):
        logger.error('Insufficient environment information, either no environment or number specified')

        return

    if env_name and env_num:
        subst_list.append('[env_name]')
        subst_list.append('[env_num]')
        input_list.append(env_name)
        input_list.append(env_num)

    subst_dict = {}
    for i, value in enumerate(subst_list):
        subst_dict[subst_list[i]] = input_list[i]

    pattern = r'\[([_a-zA-Z0-9-\s]+)\]'
    replacer = token_replacer_factory(subst_dict)
    required_cfg_files = []

    for cfg in config_files:
        new_cfg = re.sub(pattern, replacer, cfg)
        path_to_cfg = os.path.join(location, new_cfg + suffix)
        required_cfg_files.append(path_to_cfg)
        logger.info('Added configuration file: %s', path_to_cfg)

    return required_cfg_files


def read_substitution_file(file_name, field_separator):
    config_dict = dict()
    logger.info('Processing Config File: %s', file_name)
    with open(file_name, 'r') as fil:
        for line in fil:
            # Regex Matches lines starting with whitespace
            if not re.match(r'^\s*$', line) and not line.startswith('#'):
                config_values = line.split(field_separator, 1)
                config_id = '[' + config_values[0] + ']'
                config_dict[config_id] = config_values[1].rstrip()
                logger.debug('Found Config Key: %s', config_id)
                logger.debug('Found Config Value: %s', config_values[1].rstrip())
        return config_dict


def validate_files(file_list):
    files_missing = []
    for each_file in file_list:
        if not os.path.isfile(each_file):
            files_missing.append(each_file)
    return files_missing
