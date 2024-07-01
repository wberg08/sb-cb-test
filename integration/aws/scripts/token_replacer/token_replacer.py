from __future__ import absolute_import
import re
import os
from os.path import isfile, join
import argparse
import logging
import modules.config_files
from shutil import copyfile

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

IGNORE_CONTENT_TOKENS_EXTENSIONS = ('.py', '.template', '.md','.java')
EXECUTABLE_EXTENSIONS = ('.sh', '.py')

# Pattern matches letters, numbers and - or _ in brackets.
# if tokens have other special characters they will not be read.
TOKEN_REGEX = r'\[([_a-zA-Z0-9-\s]+)\]'


def token_conversion(text, subst_dict, remove_dictionary):

    replacer = modules.config_files.token_replacer_factory(subst_dict)
    new_file = re.sub(TOKEN_REGEX, replacer, text)

    # Remove lines if redundant (used for removing parameters from YAML's)
    if remove_dictionary:
        new_file = remove_redundant_lines(new_file, remove_dictionary)

    return new_file


def remove_redundant_lines(text, lines_to_remove):
    for string in lines_to_remove:
        pattern = r'.*' + re.escape(string) + r'.*\n'
        logger.debug(pattern)
        if re.search(pattern, text, re.IGNORECASE):
            logger.info('Removing line containinig: %s', string)
            text = re.sub(pattern, '', text)
    return text


def print_dup_names(duplist):
    for name, duplicate in duplist:
        for dd in duplicate:
            pj = os.path.normpath(os.path.join(dd, name))
            logger.info(pj)


def add_if_file(allfiles, dirname, fil):
    if os.path.isfile(os.path.join(dirname, fil)):
        if fil in allfiles:
            allfiles[fil].append(dirname)
        else:
            allfiles[fil] = [dirname]


def has_duplicates(modules_path):
    logger.info('Checking for duplicate filenames before flattening in path: %s', modules_path)

    # Traverse folders.
    walk_files = list(os.walk(modules_path))

    # Extract 'all' filenames.
    all_files = []
    for _, _, files in walk_files:
        all_files += files

    # Log filenames if duplicates found.
    duplicates = set(i for i in all_files if all_files.count(i) > 1)
    if len(duplicates) != 0:
        logger.info('Duplicate filenames found: %s', duplicates)

    # Use 'set' to remove duplicates.
    has_duplicates = len(all_files) != len(set(all_files))
    return has_duplicates


def create_target_directory(dir_path):
    try:
        os.makedirs(dir_path)
    except OSError:
        if not os.path.isdir(dir_path):
            raise


def get_available_modules(modules_path):
    logger.info('Getting available modules from %s', modules_path)
    modules_list = os.listdir(modules_path)
    if modules_list:
        logger.info('Available modules: %s', str(modules_list))
    else:
        logger.error('No modules found!')
    return modules_list


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


def get_excluded_modules(required_modules, available_modules):
    excluded_modules = list(set(available_modules).difference(required_modules))
    if excluded_modules:
        logger.info('Excluding the following modules from environment: %s', str(excluded_modules))
    return excluded_modules


def validate_modules(available_modules, required_modules):
    missing_modules = (set(required_modules).difference(available_modules))
    missing_modules = ', '.join(missing_modules)
    if missing_modules:
        logger.error('Environment requires modules that do not exist: %s', str(missing_modules))
    logger.info('Environment modules validated')
    return missing_modules


def check_orphan_tokens(path):
    # Checks for remaining tokens at the end of the build process.
    orphan_tokens = []
    for (dirpath, dirnames, filenames) in os.walk('./' + path):
        for filename in filenames:
            if not filename.endswith(IGNORE_CONTENT_TOKENS_EXTENSIONS):
                file_path = join(dirpath, filename)
                logger.debug('Checking %s for orphan tokens', file_path)
                text = open(file_path, 'r')
                for line in text:
                    if re.search(TOKEN_REGEX, line):
                        orphan_tokens.append(line)
    return orphan_tokens


def get_config_value(dictionary, key):
    value = dictionary.get('[' + key + ']')
    if not value:
        logger.warning('key %s not found in dictionary', key)
    return value


def set_networking_configuration(dictionary):
    # Check if zone dictionary value is available
    if get_config_value(dictionary, 'active_zone_count') != None:
        # Normal Subnets
        logger.info('Processing environment to modify networking settings')
        lines_to_delete = []
        active_zone_count = int(get_config_value(dictionary, 'active_zone_count'))
        logger.info('Active zone count is: %s', str(active_zone_count))
        if active_zone_count == 1:
            logger.debug('Removing subnet references not required for single active zone')
            lines_to_delete.append('oSnMgtPublicB')
            lines_to_delete.append('oSnPrePublicB')
            lines_to_delete.append('oSnMgtPrivateB')
            lines_to_delete.append('oSnPrePrivateB')
            lines_to_delete.append('oSnAppPrivateB')
            # EIPs For NAT Gateways
            lines_to_delete.append('oEipIdNat01b')

        if active_zone_count < 3:
            logger.debug('Removing subnet references not required when using less than 3 zones')
            lines_to_delete.append('oSnMgtPublicC')
            lines_to_delete.append('oSnPrePublicC')
            lines_to_delete.append('oSnMgtPrivateC')
            lines_to_delete.append('oSnPrePrivateC')
            lines_to_delete.append('oSnAppPrivateC')

            # Super Special RDS and ELBs I must have at least 2 zones subnets.
            logger.debug(
                'Removing database and elb subnet references not required when using less than 3 zones'
            )
            lines_to_delete.append('oSnDatPrivateC')
            lines_to_delete.append('oSnElbPublicC')
            lines_to_delete.append('oSnElbPrivateC')
            lines_to_delete.append('eu-west-1c')
            # EIPs For NAT Gateways
            lines_to_delete.append('oEipIdNat01c')

        logger.debug('Lines to remove: %s', str(lines_to_delete))

        return lines_to_delete

    else:
        logger.info('Active zone count is not available for deployment, skipping')


def make_executable(path):
    mode = os.stat(path).st_mode
    mode |= (mode & 0o444) >> 2  # copy R bits to X
    os.chmod(path, mode)


def replace_tokens(
        target_project, target_account, build_type, base_path, build_config, target_env_name=None, target_env_num=None
):
    # Set environment information if present
    if not 'target_env_name' or not 'target_env_num' and build_type.lower() == "environment":
        logger.error(
            'Not all environment information was passed. Environment Name:, %s Environment Number: %s', target_env_name,
            target_env_num
        )

    # Read Configuration from build.yml into Variables
    config_file_suffix = build_config['config']['suffix']
    transforms_location = build_config['config']['source']
    modules_config_prefix = build_config['modules'][build_type]['prefix']
    build_output_root_location = build_config['modules']['target']
    build_output_type_location = build_config['modules'][build_type]['target']
    modules_location = build_config['modules'][build_type]['source']

    logger.info('Base Path = %s', base_path)

    # Set paths
    transforms_path = os.path.join(base_path, transforms_location)
    logger.info('Transforms Path = %s', transforms_path)
    modules_path = os.path.join(base_path, modules_location)
    logger.info('Modules Path = %s', modules_path)

    # # Check for conflicting module resources
    if has_duplicates(modules_path):
        message = 'Conflicting module resources found, this could lead to bad updates. Aborting'
        logger.error(message)
        raise RuntimeError(message)

    # Load up appropriate config files and check if they exist
    logger.info('Loading Transforms configuration')

    file_list = []

    # Target output directory where new code will be created.
    if build_type.lower() == "environment":
        build_output_path = os.path.join(
            base_path, build_output_root_location,
            build_output_type_location,
            target_project, target_account,
            target_env_name + target_env_num
        )

        # Set transform files
        file_list = modules.config_files.get_transform_configs(build_config, build_type, transforms_path,
                                                               config_file_suffix,
                                                               target_project, target_account, target_env_name,
                                                               target_env_num)

    elif build_type.lower() == "account":
        build_output_path = os.path.join(
            base_path, build_output_root_location,
            build_output_type_location,
            target_project, target_account
        )
        file_list = modules.config_files.get_transform_configs(build_config, build_type, transforms_path,
                                                               config_file_suffix,
                                                               target_project, target_account)
    else:
        message = 'Unknown build type {}'.format(build_type)

    logger.info('Output path for %s = %s', build_type, build_output_path)

    # Check all the configuration files are present
    missing_files = modules.config_files.validate_files(file_list)
    if missing_files:
        message = 'Configuration files are missing aborting build: {}'.format(missing_files)
        raise RuntimeError(message)

    # Load substitution variables
    logger.info('Reading tokens for substitution')
    subst_dict = dict()
    for fil in file_list:
        if isfile(fil):
            subst_dict.update(modules.config_files.read_substitution_file(fil, '='))
    logger.debug('Config dictionary contents: %s', subst_dict)

    # Get strings to match lines for removal (subnets etc.)
    lines_to_remove = set_networking_configuration(subst_dict)

    # Get required modules and available modules
    required_modules = get_required_modules(subst_dict, modules_config_prefix)
    available_modules = get_available_modules(modules_path)

    # Check if we are missing any modules required to build environment
    missing_modules = validate_modules(available_modules, required_modules)
    if missing_modules:
        message = 'Missing modules, cannot build environment'
        raise RuntimeError(message)

    # Check if folder already exists and create
    if not os.path.exists(build_output_path):
        logger.info('Creating target directory: %s', build_output_path)
        create_target_directory(build_output_path)
    else:
        message = 'Environment already exists, workspace is not clean. Aborting.'
        raise RuntimeError(message)

    # read all files in the modules path
    # rename them, subst values and write out

    # W Work out which modules should be excluded.
    excluded_modules = get_excluded_modules(required_modules, available_modules)

    logger.info('Importing and Transforming required Modules into Environment')

    # Get the contents of the module directory
    for (dirpath, dirnames, filenames) in os.walk('./' + modules_path, topdown=True):

        # Check for excluded module name in directory path to file, ignore if a match is found
        if not any(
            '/{}/'.format(module) in dirpath or
            dirpath.endswith('/{}'.format(module))
            for module in excluded_modules
        ):
            # Copy and token replace each file into generated code location
            for filename in filenames:
                if filename:
                    rel_path = os.path.relpath(dirpath, './' + modules_path)
                    logger.debug('Relative Path = %s', rel_path)

                    # Remove the 1st leading slash so we can rebuild as an exact path.
                    real_path = '/'.join(rel_path.strip('/').split('/')[1:])
                    destination_path = os.path.join(build_output_path, real_path)
                    logger.debug('Destination = %s', destination_path)
                    if not os.path.exists(destination_path):
                        create_target_directory(destination_path)

                    # Process file name which can contain tokens
                    target_filename = token_conversion(filename, subst_dict, lines_to_remove)
                    logger.info('Target File: %s', target_filename)

                    source_file_path = join(dirpath, filename)
                    destination_file_path = join(destination_path, target_filename)

                    if filename.endswith(IGNORE_CONTENT_TOKENS_EXTENSIONS):
                        logger.info('Copied file %s without token conversion', target_filename)
                        copyfile(source_file_path, destination_file_path)
                    else:
                        with open(source_file_path, 'r') as current_file:
                            logger.debug('Starting process build file: %s', target_filename)

                            with open(destination_file_path, 'w+') as output_file:
                                output_file.write(
                                    token_conversion(current_file.read(),
                                                     subst_dict, lines_to_remove)
                                )
                                if target_filename.endswith(EXECUTABLE_EXTENSIONS):
                                    make_executable(destination_file_path)
                            logger.debug('Finished processing build file: %s', target_filename)

        else:
            logger.info('Excluding path: %s as its part of excluded module', dirpath)

    # Read all files in new environment path and check for orphan tokens
    logger.info('Checking generated Environment code for orphan tokens')
    orphan_tokens = check_orphan_tokens('./' + build_output_path)
    if orphan_tokens:
        message = 'Environment code may not deployable, there are unsubstituted tokens detected'
        logger.error(message)
        logger.info(orphan_tokens)
        raise RuntimeError(message)

    logger.info(
        'Environment %s%s for project %s in account: %s generated successfully',
        target_env_name, target_env_num, target_project, target_account
    )


def main():
    # Check input parameters are as required
    parser = argparse.ArgumentParser('Token substitution for deployment files')
    parser.add_argument(
        'target_project', help='Name of target project e.g. portal', required=True
    )
    parser.add_argument(
        'target_account', help='Name of target AWS account e.g. KcomTropoHmrcDev', required=True
    )
    parser.add_argument(
        'target_env_name', help='Name of target AWS environment e.g. Dev', required=False
    )
    parser.add_argument(
        'target_env_num', help='Number of the target AWS environment e.g. 01', required=False
    )
    parser.add_argument(
        'base_path', help='Directory location to use for file processing', required=True
    )
    parser.add_argument(
        'build_config', help='Build Configuration', required=True
    )
    parser.add_argument(
        'build_type', help='Type of build, e.g environment or account', required=True
    )
    args = parser.parse_args()

    replace_tokens(
        args.target_project, args.target_account,
        args.build_type, args.base_path, args.build_config,
        args.target_env_name, args.target_env_num
    )

    if __name__ == '__main__':
        main()
