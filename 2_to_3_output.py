import json
import logging
import os
import sys


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--path",
                        default='output',
                        required=False)
    args = parser.parse_args()

    logger = logging.getLogger('2_to_3_output')
    if not logger.hasHandlers():
        formatter = logging.Formatter(fmt='{asctime}.{msecs:0<3.0f} {name} {threadName} {levelname}: {message}',
                                      style='{',
                                      datefmt='%Y-%m-%d %H:%M:%S')
        formatter.default_msec_format = '%s.%03d'
        screen_handler = logging.StreamHandler(stream=sys.stderr)
        screen_handler.setFormatter(formatter)
        screen_handler.setLevel(logging.INFO)
        logger.setLevel(logging.INFO)
        logger.addHandler(screen_handler)

    output_path_file_list = next(os.walk(args.path), (None, None, []))[2]
    for output_file_name in output_path_file_list:
        if not output_file_name.endswith('.json'):
            logger.warning(f'Skipping non-json file {output_file_name}.')
            continue
        logger.info(f'Processing {output_file_name}...')
        with open(os.path.join(args.path, output_file_name), 'r') as output_file:
            os.makedirs(f'{args.path}_refactored', exist_ok=True)
            try:
                source = json.load(output_file)
            except json.decoder.JSONDecodeError as e:
                logger.error(f'Failed to parse {output_file_name}, {e.msg}', exc_info=e)
                continue
            if type(source) is not list:
                logger.error(f'{output_file_name} skipped because it is not a JSON array')
                continue
            with open(os.path.join(f'{args.path}_refactored', output_file_name), 'w') as refactored_output_file:
                for line in source:
                    json.dump(line, refactored_output_file)
                    refactored_output_file.write('\n')
        logger.info(f'Done refactoring {output_file_name} to {args.path}_refactored/{output_file_name}')


if __name__ == '__main__':
    main()