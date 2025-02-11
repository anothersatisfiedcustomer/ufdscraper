#!/usr/bin/env python3
import datetime
import logging
import os
import json
import random
import ssl
import string
import sys
from json import JSONDecodeError
from time import sleep
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class UFDError(Exception):
    def __init__(self, ex):
        super().__init__(ex)


class LoginError(UFDError):
    def __init__(self, ex):
        super().__init__(ex)


class ContractError(UFDError):
    def __init__(self, ex):
        super().__init__(ex)


class ConsumptionError(UFDError):
    def __init__(self, ex):
        super().__init__(ex)


class UFDScraper:
    _DEFAULT_API_BASE_URL = 'https://api.ufd.es/ufd/v1.0/'
    _DEFAULT_API_SERVER_SSL_CERT_VERIFY = True
    _DEFAULT_PORTAL_BASE_URL = 'https://areaprivada.ufd.es'
    _DEFAULT_WEB_APP_ID = 'ACUFD'
    _DEFAULT_WEB_APP_CLIENT_REFERENCE = 'ACUFDW'
    _DEFAULT_WEB_APP_API_CLIENT_ID = '1f3n1frmnqn14arndr3507lnok'
    _DEFAULT_WEB_APP_API_CLIENT_SECRET = '102sml3ajvkdjakoh2rhgrfpvjogl4b0or5nqmcmilvt2odpu9ce'
    _DEFAULT_USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)' + \
        'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/96.0.4664.110 Safari/537.36'
    _DEFAULT_MIN_S_BETWEEN_API_CALLS = 2
    _DEFAULT_MAX_S_BETWEEN_API_CALLS = 4
    _DEFAULT_TOKEN_VALIDITY_IN_S = 60

    def __init__(self, logger=None, config=None):
        self._logger = logger or logging.getLogger(__name__)
        if not config:
            config = {}
        self._user = config.get('ufd_account_login', None)
        self._password = config.get('ufd_account_password', None)
        self._token_validity_in_s = config.get('ufd_token_validity_in_s', self._DEFAULT_TOKEN_VALIDITY_IN_S)
        self._last_login_datetime = datetime.datetime.fromtimestamp(0)
        self._api_base_url = config.get('api_base_url', self._DEFAULT_API_BASE_URL)
        self._verify = config.get('api_server_ssl_cert_verify', self._DEFAULT_API_SERVER_SSL_CERT_VERIFY)
        self._portal_base_url = config.get('portal_base_url', self._DEFAULT_PORTAL_BASE_URL)
        self._web_app_id = config.get('web_app_id', self._DEFAULT_WEB_APP_ID)
        self._web_app_client_reference = config.get('web_app_client_reference', self._DEFAULT_WEB_APP_CLIENT_REFERENCE)
        self._web_app_api_client_id = config.get('web_app_api_client_id', self._DEFAULT_WEB_APP_API_CLIENT_ID)
        self._web_app_api_client_secret = config.get(
            'web_app_api_client_secret', self._DEFAULT_WEB_APP_API_CLIENT_SECRET)
        self._user_agent = config.get('user_agent', self._DEFAULT_USER_AGENT)
        self._min_seconds_between_api_calls = config.get(
            'min_s_between_api_calls', self._DEFAULT_MIN_S_BETWEEN_API_CALLS)
        self._max_seconds_between_api_calls = config.get(
            'max_s_between_api_calls', self._DEFAULT_MAX_S_BETWEEN_API_CALLS)

        self._userid = '0'
        self._session_id = ''.join(random.choices(string.ascii_letters, k=15))
        self._req_no = 0
        self._access_token = None
        self._refresh_token = None
        self._expires_in_token = None

    def _ufd_api_call(self, method, url, data=None, skip_token_check=False):
        if not skip_token_check:
            self._check_refresh_token()
        self._sleep_random()
        content_length = len(data) if data else 0
        headers = self._build_request_headers(content_length)
        # build request
        req = Request(url)
        req.method = method
        ctx = ssl.create_default_context()
        if not self._verify:
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
        if data:
            req.data = bytes(f'{data}', 'utf-8')
        if headers:
            for header in headers:
                req.add_header(header, headers[header])
        response = self._process_ufd_api_call_response(req, ctx)
        self._req_no += 1
        return response

    def _process_ufd_api_call_response(self, req, ctx):
        try:
            response_raw = urlopen(req, context=ctx).read().decode("utf-8")
            self._logger.info(response_raw)
            response = json.loads(response_raw)
            if response['result']['codResult'] != '0000':
                if response['result']['codResult'] == '1007':
                    self._logger.warning(
                        f'Unexpected response from UFD API (No data in range for {req.full_url}): {response}')
                    return {}
                self._logger.error(f'Unexpected response from UFD API: {response}')
                raise ContractError('Unexpected response from UFD API')
            return response
        except HTTPError as e:
            self._logger.error(f'Error response from UFD API: {e.code}, {e.reason}')
            raise ContractError(e)
        except URLError as e:
            self._logger.error(f'Error response from UFD API: {e.reason}')
            raise ContractError(e)
        except JSONDecodeError as e:
            self._logger.error(f'Error parsing response from UFD API: {e.msg}')
            raise ContractError(e)
        except TypeError as e:
            self._logger.error(f'Error parsing response from UFD API: {e}')
            raise ContractError(e)
        except Exception as e:
            self._logger.error(f'Error parsing response from UFD API: {e}')
            raise ContractError(e)

    def _check_refresh_token(self):
        # TODO: Use actual token refresh instead of login back in to get a fresh one
        current_datetime = datetime.datetime.now()
        if (current_datetime - self._last_login_datetime).seconds > self._token_validity_in_s:
            self._login(self._user, self._password)

    def _login(self, user, password):
        if not self._user or not self._password:
            self._logger.error("missing credentials")
            return None
        self._access_token = None
        try:
            self._userid = '0'
            self._session_id = ''.join(random.choices(string.ascii_letters, k=15))
            self._req_no = 0
            url = self._api_base_url + 'login'
            data = json.dumps({"user": user, "password": password})

            response_content = self._ufd_api_call('POST', url, data=data, skip_token_check=True)

            self._access_token = response_content['accessToken']
            self._refresh_token = response_content['refreshToken']
            self._userid = response_content['user']['userId']
            self._last_login_datetime = datetime.datetime.now()
            return self._access_token, self._userid
        except Exception as ex:
            raise LoginError(ex)

    def _get_supply_point_cups(self, nif):
        try:
            url = self._api_base_url + 'supplypoints?filter=documentNumber::' + nif
            response_content = self._ufd_api_call('GET', url)
            return response_content['supplyPoints']['items'][0]['cups']
        except Exception as ex:
            raise ContractError(ex)

    def _get_hourly_consumption_for_day(self, day_string, nif, contract):
        try:
            url = self._api_base_url + 'consumptions?filter=nif::' + nif + '%7Ccups::' + contract + '%7CstartDate::' + \
                  day_string + '%7CendDate::' + day_string + \
                  '%7Cgranularity::H%7Cunit::K%7Cgenerator::0' + \
                  '%7CisDelegate::N%7CisSelfConsumption::0%7CmeasurementSystem::O'
            response_content = self._ufd_api_call('GET', url)
            response_content['tags'] = { 'cups': contract }
            return response_content
        except Exception as ex:
            raise ConsumptionError(ex)

    def _build_request_headers(self, content_length=0):
        headers = {
            'Accept': 'application/json',
            'Accept-Language': 'es-ES',
            'Access-Control-Allow-Headers': 'Origin, X-Requested-With, Content-Type, Accept',
            'Access-Control-Allow-Origin': '*',
            'Content-Type': 'application/json',
            'Origin': self._portal_base_url,
            'Referer': self._portal_base_url + '/',
            'Sec-Ch-Ua': '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
            'Sec-Ch-Ua-Mobile': '?0',
            'Sec-Ch-Ua-Platform': '"Windows"',
            'Sec-Fetch-Dest': 'empty',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Site': 'same-site',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'X-AppClient': self._web_app_client_reference,
            'X-Appclientid': self._web_app_api_client_id,
            'X-AppClientSecret': self._web_app_api_client_secret,
            'X-Application': self._web_app_id,
            'X-Appversion': '1.0.0.0',
            'X-MessageId': self._userid + '/' + self._session_id + '/' + str(self._req_no),
        }
        if content_length:
            headers['Content-Length'] = content_length
        if self._access_token:
            headers['Authorization'] = 'Bearer ' + self._access_token
        return headers

    def _sleep_random(self):
        sleep_seconds = random.randint(self._min_seconds_between_api_calls, self._max_seconds_between_api_calls)
        self._logger.info('Sleeping ' + str(sleep_seconds) + 's before next request...')
        sleep(sleep_seconds)

    def scrap_ufd(self, ini_date, end_date, output_file_name = None):
        try:
            customer_nif = self._user
            contract_id = self._get_supply_point_cups(nif=customer_nif)
            cur_date = end_date
            days = (end_date - ini_date + datetime.timedelta(1)).days
            shift = datetime.timedelta(1)

            if not output_file_name:
                for _ in range(days):
                    print(json.dumps(self._get_hourly_consumption_for_day(cur_date.strftime('%d/%m/%Y'),
                                                                           nif=customer_nif,
                                                                           contract=contract_id)))
                    cur_date = cur_date - shift
            else:
                with open(output_file_name, 'w') as output_file:
                    for _ in range(days):
                        result = self._get_hourly_consumption_for_day(cur_date.strftime('%d/%m/%Y'),
                                                                      nif=customer_nif,
                                                                      contract=contract_id)
                        self._logger.info(result)
                        if result:
                            json.dump(result, output_file)
                            output_file.write('\n')
                        cur_date = cur_date - shift
        except Exception as e:
            self._logger.error(e)


def main():
    default_start = (datetime.datetime.now().replace(day=1) - datetime.timedelta(1)).replace(day=1).strftime('%Y%m%d')
    default_end = (datetime.datetime.now().replace(day=1) - datetime.timedelta(1)).strftime('%Y%m%d')
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--start",
                        default=default_start,
                        required=False)
    parser.add_argument("--end",
                        default=default_end,
                        required=False)
    parser.add_argument("--dump-to-file", default=False, action="store_true")
    parser.add_argument("--no-ssl-verify", default=False, action="store_true")
    args = parser.parse_args()
    start = args.start if args.start else default_start
    end = args.end if args.end else default_end
    output_file_name = os.path.join('output', 'output_from_' + start + '_to_' + end
                                    + '_at_' + datetime.datetime.now().strftime('%Y%m%d_%H%M%S') + '.json')
    config = {'ufd_account_login': os.environ.get('USER'),
              'ufd_account_password': os.environ.get('PASSWORD'),
              'api_server_ssl_cert_verify': False if args.no_ssl_verify else True}

    logger = logging.getLogger('ufdscraper')
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
    us = UFDScraper(logger, config)
    us.scrap_ufd(
        datetime.datetime.strptime(start, '%Y%m%d'),
        datetime.datetime.strptime(end, '%Y%m%d'),
        output_file_name if args.dump_to_file else None
    )


if __name__ == '__main__':
    main()
