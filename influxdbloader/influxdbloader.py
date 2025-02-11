#!/usr/bin/env python3
import os
import json
import logging
import datetime
import sys
from zoneinfo import ZoneInfo

from influxdb import InfluxDBClient


class InfluxDBLoader:

    def __init__(self, logger, config):
        self._logger = logger or logging.getLogger(__name__)
        self._init_extension(config)
        self._influx_source = config.get('influx_source', 'ufd_01')
        self._tags = config.get('influx_tags', self._DEFAULT_TAGS)

    @staticmethod
    def _float_or_string(x):
        try:
            return float(x.replace(',','.'))
        except (AttributeError, ValueError):
            return x

    def _map_reading(self, reading, influx_source):
        mapped_reading = []
        hourly_consumptions = reading.get('items', [[]])[0].get('consumptions', {}).get('items', [])
        for hour_consumptions in hourly_consumptions:
            try:
                hour = int(hour_consumptions.get('hour', 1)) - 1
                consumption_date = [int(i) for i in hour_consumptions.get('consumptionDate',"31/1/1001").split('/')]
                timestamp = datetime.datetime(
                    year=consumption_date[2],
                    month=consumption_date[1],
                    day=consumption_date[0],
                    hour=hour,
                    tzinfo=ZoneInfo("Europe/Madrid")
                )
                fields = {key: InfluxDBLoader._float_or_string(hour_consumptions[key]) for key in hour_consumptions.keys() if
                          key != 'hour' and key != 'consumptionDate' and hour_consumptions[key]}
                mapped_reading.append({
                    'measurement': influx_source,
                    'time': timestamp,
                    'tags': self._tags,
                    'fields': fields
                })
            except Exception as e:
                self._logger.error(f'Failed to map reading {json.dumps(reading)}', exc_info=e)
        return mapped_reading

    def _format(self, readings):
        formatted_readings = []
        formatted_readings.extend(self._map_reading(readings, self._influx_source))
        return formatted_readings

    def _init_extension(self, config):
        self._hostname = config.get('hostname', self._DEFAULT_HOSTNAME)
        self._port = config.get('port', self._DEFAULT_PORT)
        self._user = config.get('user', self._DEFAULT_USER)
        self._password = config.get('password', self._DEFAULT_PASSWORD)
        self._database = config.get('database', self._DEFAULT_DATABASE)
        self._retention_policy = config.get('retention_policy', self._DEFAULT_RETENTION_POLICY)
        if not self._retention_policy:
            self._retention_policy = self._DEFAULT_RETENTION_POLICY
        try:
            self._init_client()
        except Exception as err:
            self._logger.warning(
                f'Error connecting to influxdb on host: {self._hostname} port: {self._port} user: {self._user} database: {self._database}')
            self._logger.warning(err, exc_info=err)

    def push(self, scrapped_readings):
        mapped_readings = self._format(scrapped_readings)
        try:
            self._client.write_points(
                mapped_readings,
                retention_policy=self._retention_policy,
                database=self._database,
                tags={})
            self._logger.debug(f'{len(mapped_readings)} points persisted successfully')
        except Exception as err:
            self._logger.warning(
                f'Error writing points to influxdb on host: {self._hostname} port: {self._port} user: {self._user} database: {self._database}')
            self._logger.warning(err, exc_info=err)

    _DEFAULT_HOSTNAME = 'localhost'
    _DEFAULT_PORT = 8086
    _DEFAULT_USER = 'root'
    _DEFAULT_PASSWORD = 'root'
    _DEFAULT_DATABASE = None
    _DEFAULT_RETENTION_POLICY = None

    _DEFAULT_TAGS = {}

    def _init_client(self):
        self._client = InfluxDBClient(self._hostname, self._port, self._user,
                                      self._password, self._database)
        return self._client


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--host",
                        default='localhost',
                        required=False)
    parser.add_argument("--port",
                        default=8086,
                        required=False)
    parser.add_argument("--database",
                        default='ufddb',
                        required=False)
    parser.add_argument("--source",
                        default='ufd_01',
                        required=False)
    parser.add_argument("--retention-policy",
                        default=None,
                        required=False)
    parser.add_argument("--path",
                        default='output',
                        required=False)
    args = parser.parse_args()
    config = {'user': os.environ.get('INFLUXDB_USER'),
              'password': os.environ.get('INFLUXDB_PASSWORD'),
              'hostname': args.host,
              'port': args.port,
              'database': args.database,
              'retention_policy': args.retention_policy,
              'influx_source': args.source }
    logger = logging.getLogger('influxdbloader')
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
    il = InfluxDBLoader(logger, config)

    output_path_file_list = next(os.walk(args.path), (None, None, []))[2]

    for output_file_name in output_path_file_list:
        logger.warning(f'Processing {output_file_name}...')
        with open(os.path.join(args.path, output_file_name), 'r') as output_file:
            jsonlines = map(json.loads, output_file)
            for jsonline in jsonlines:
                il.push(jsonline)
        logger.warning(f'Done processing {output_file_name}')


if __name__ == '__main__':
    main()
