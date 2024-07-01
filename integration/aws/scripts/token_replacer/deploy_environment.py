#!/usr/bin/env python

# usage deploy_environment -f ./integration/aws/build.yml -e dev -n 01 -p sb -a kcomiamsbshared
# -r myrolearn -rc mycmnsrolearn -sn mysession -b ./integration/aws

from __future__ import absolute_import
import argparse
import logging
from os.path import isfile
import modules.config_files
import re
import os
import subprocess  # pylint: disable=B404
import shlex

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

parser = argparse.ArgumentParser(description='Infrastructure environment builder.')
parser.add_argument(
    '-f', '--build_config',
    help='YAML configuration file containing environments to be built', required=True
)
parser.add_argument(
    '-e', '--environment_name',
    help='Name of account to deploy', required=False
)
parser.add_argument(
    '-n', '--environment_number',
    help='Number of account to deploy', required=False
)
parser.add_argument(
    '-a', '--account_name',
    help='Name of account to deploy into', required=True
)
parser.add_argument(
    '-p', '--project_name',
    help='Name of project to deploy into', required=True
)
parser.add_argument(
    '-r', '--role_arn',
    help='Role to use to deploy environment', required=True
)
parser.add_argument(
    '-rc', '--cmns_role_arn',
    help='Role to use to deploy resources to common environment', required=False
)
parser.add_argument(
    '-sn', '--session_name',
    help='Session name to use for tracking within CloudTrail', required=True
)
parser.add_argument(
    '-b', '--base_path',
    help='Base path for builds', required=True
)
parser.add_argument(
    '-t', '--build_type',
    default='environment',
    choices=['environment', 'account'],
    help='Type of deployment, account or environment currently supported.', required=False
)
parser.add_argument(
    '-m', '--mode',
    default='create',
    choices=['create', 'remove', 'update'],
    help='Flag to create or destroy environment', required=False
)

args = parser.parse_args()


def get_required_modules(subst_dict, modules_config_prefix):
    required_modules = []
    for subst in subst_dict:
        pattern = r'([_a-zA-Z0-9-\s]+)'
        module_name = re.findall(pattern, subst)
        module_name = module_name[0]
        if module_name.startswith(modules_config_prefix):
            module_name = module_name[len(modules_config_prefix):]
            module_active = subst_dict.get(subst)
            if module_active == 'True' or module_active == 'true':
                logger.debug('Adding module: %s', module_name)
                required_modules.append(module_name)
    logger.info('Required modules: %s', str(required_modules))
    return required_modules


def validate_order(modules_ordering, required_modules):
    missing_ordering = (set(required_modules).difference(modules_ordering))
    missing_ordering = ', '.join(missing_ordering)
    logger.info('ordering missing for files: %s', missing_ordering)

    if missing_ordering:
        logger.error('No ordering information available for modules: %s', str(missing_ordering))
    return missing_ordering


def check_allow_remove_flag(build_type, cfg):
    # Check removal flag allows for automated removal.

    if build_type == "account":
        allow_remove = cfg['projects'][args.project_name]['accounts'][args.account_name].get(
            'allow_remove', False)

    elif build_type == "environment":
        environment = args.environment_name + args.environment_number
        allow_remove = cfg['projects'][args.project_name]['accounts'][args.account_name]['environments'][
            environment].get('allow_remove', False)

    else:
        allow_remove = False

    return allow_remove

    # Work out if it's environment or account level deployment, account level is
    # for resources which can only exist once per account.


def check_build_config(build_type, cfg):
    # Check removal flag allows for automated removal.

    if build_type == "account":
        build_config = cfg['projects'][args.project_name]['accounts'][args.account_name].get(
            'config', 'blue')

    elif build_type == "environment":
        environment = args.environment_name + args.environment_number
        build_config = cfg['projects'][args.project_name]['accounts'][args.account_name]['environments'][
            environment].get('config', 'blue')

    else:
        build_config = "blue"

    return build_config.lower()


def deploy(build_config, base_path):
    # Read Configuration from build.yml into Variables

    cfg = modules.config_files.load_build_configs(build_config)
    logger.debug(cfg)

    config_file_suffix = cfg['config']['suffix']
    transforms_location = cfg['config']['source']
    modules_config_prefix = cfg['modules'][args.build_type]['prefix']
    build_output_root_location = cfg['modules']['target']
    build_output_type_location = cfg['modules'][args.build_type]['target']
    deploy_file_suffix = cfg['deployment']['suffix']

    remove_environment = check_allow_remove_flag(args.build_type, cfg)
    if remove_environment == False and args.mode == "remove":
        message = '{} cannot be removed via script as allow_remove is set to false in the build.yml'.format(
            args.build_type)
        raise RuntimeError(message)

    transforms_path = os.path.join(base_path, transforms_location)

    # Set Blue / Green configuration state

    build_config = check_build_config(args.build_type, cfg)

    # Set deployers location.

    logger.info('Loading Transforms configuration')

    file_list = []

    if args.build_type.lower() == "environment":
        deployers_location = os.path.join(
            base_path, build_output_root_location,
            build_output_type_location,
            args.project_name, args.account_name,
            args.environment_name + args.environment_number
        )

        # Set transform files
        file_list = modules.config_files.get_transform_configs(
            cfg, args.build_type, transforms_path, config_file_suffix,
            args.project_name, args.account_name, args.environment_name,
            args.environment_number)

    elif args.build_type.lower() == "account":
        deployers_location = os.path.join(
            base_path, build_output_root_location,
            build_output_type_location,
            args.project_name, args.account_name,
        )

        # Set transform files
        file_list = modules.config_files.get_transform_configs(
            cfg, args.build_type, transforms_path, config_file_suffix,
            args.project_name, args.account_name)
    else:
        message = 'Unknown deploy type {}'.format(args.build_type)
        raise RuntimeError(message)

    logger.info('Module deployment scripts location %s', deployers_location)

    # Get module deployment order
    modules_order = cfg['modules'][args.build_type]['ordering']
    logger.debug("Modules will be processed in the following order %s", modules_order)

    logger.info('Base Path = %s', base_path)

    # Set paths
    transforms_path = os.path.join(base_path, transforms_location)
    logger.info('Transforms Path = %s', transforms_path)

    # Check all the configuration files are present
    missing_config_files = modules.config_files.validate_files(file_list)
    if missing_config_files:
        message = 'Configuration files are missing aborting build: {}'.format(missing_config_files)
        raise RuntimeError(message)

    # Load substitution variables
    logger.info('Reading tokens for substitution')
    subst_dict = dict()
    for fil in file_list:
        if isfile(fil):
            subst_dict.update(modules.config_files.read_substitution_file(fil, '='))

    # Get required modules
    required_modules = get_required_modules(subst_dict, modules_config_prefix)
    logger.info(
        'Required modules for deployment: %s', required_modules
    )
    required_deployers_full_path = []
    for module in required_modules:
        deployer_path = os.path.join(deployers_location, module + deploy_file_suffix)
        required_deployers_full_path.append(deployer_path)
    logger.info(
        'Required deployers: %s', required_deployers_full_path
    )

    # Check all the deployers are present for the modules.
    missing_deployers = modules.config_files.validate_files(required_deployers_full_path)
    if missing_deployers:
        message = 'Missing deployer scripts {}'.format(missing_deployers)
        raise RuntimeError(message)

    # Work out order for the modules we have
    missing_ordering = validate_order(modules_order, required_modules)
    if missing_ordering:
        message = 'Cannot deploy due to missing module run order information for: {}'.format(
            missing_ordering)
        raise RuntimeError(message)

    sorted_modules = sorted(required_modules, key=lambda x: modules_order.index(
        x))  # pylint: disable=unused-argument

    if args.mode == 'remove':
        logger.info(
            'Environment flagged for remove, reversing the module order'
        )
        sorted_modules.reverse()

    logger.info('Modules will be processed in the following order: %s', sorted_modules)

    logger.info('Modules Required: %s ', required_modules)

    for module in sorted_modules:
        deployer_path = os.path.join(deployers_location, module + deploy_file_suffix)
        if args.build_type == 'environment':
            environment_name = args.environment_name
            environment_number = args.environment_number
        else:
            environment_name = 'none'
            environment_number = 'none'

        logger.info('Running Deployer File: %s for module: %s in mode: %s with config: %s',
                    deployer_path, module, args.mode, build_config)

        process = subprocess.Popen(shlex.split(  # nosec
            deployer_path +
            ' -s ' + args.mode +
            ' -c ' + build_config +
            ' -e ' + environment_name +
            ' -n ' + environment_number +
            ' -p ' + args.project_name +
            ' -a ' + args.account_name +
            ' -r ' + args.role_arn +
            ' -rc ' + args.cmns_role_arn +
            ' -sn ' + args.session_name +
            ' -d ' + deployers_location
        ), stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        while True:
            output = process.stdout.readline().decode()
            if output == '' and process.poll() is not None:
                break
            if output:
                print(output.strip())
        rc = process.poll()
        if rc != 0:
            logger.error(
                'Running Deployer for Module: %s FAILED! exited with return code: %s',
                module,
                rc
            )
            raise RuntimeError('FAILED to successfully deploy module.')

        logger.info('Running Deployer for Module: %s SUCCEEDED!', module)


deploy(args.build_config, args.base_path)
