#!/usr/bin/env python

from __future__ import absolute_import
import argparse
import logging
import token_replacer
import modules.config_files

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

parser = argparse.ArgumentParser(description='Infrastructure code builder.')
parser.add_argument(
    '-f', '--buildconfig',
    help='YAML configuration file containing environments to be built', required=True
)

args = parser.parse_args()


def build_environments(filename):
    cfg = modules.config_files.load_build_configs(filename)
    logger.debug(cfg)
    projects = cfg['projects']

    for project_name, project in iter(projects.items()):
        logger.info('Found project %s', project_name)
        accounts = project['accounts']

        for account_name, account in iter(accounts.items()):
            logger.info('Found account %s', account_name)
            environments = account.get('environments', None)

            account_build = account['build']
            if not account_build:
                logger.info('Account %s build is %s, skipping',
                            account_name, account_build)
                break

            logger.info('Building Account: %s', account_name)
            token_replacer.replace_tokens(
                project_name, account_name, "account", "integration/aws", cfg
            )

            if environments:
                for environment_name, environment in iter(environments.items()):
                    logger.info('Found environment %s', environment_name)
                    env_name = environment['name']
                    env_num = environment['number']
                    env_build = environment['build']

                    if env_build:
                        logger.info('Building Environment: %s',
                                    env_name + env_num)
                        token_replacer.replace_tokens(
                            project_name, account_name, "environment",
                            "integration/aws", cfg,
                            env_name, env_num
                        )
                    else:
                        logger.info('Environment %s build is %s, skipping',
                                    env_name + env_num, account_build)
            else:
                logger.info('No environments for Account: %s ', account_name)


# build_environments(args.buildconfig)
logger.info('build_environments.py')
