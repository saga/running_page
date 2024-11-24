"""
Python 3 API wrapper for Garmin Connect to get your statistics.
Copy most code from https://github.com/cyberjunky/python-garminconnect
"""

import argparse
import asyncio
import logging
import os
import sys
import time
import traceback
import zipfile
from io import BytesIO

import aiofiles
import cloudscraper
import garth
import httpx
from config import FOLDER_DICT, JSON_FILE, SQL_FILE, config
from garmin_device_adaptor import wrap_device_info
from utils import make_activities_file

# logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

TIME_OUT = httpx.Timeout(240.0, connect=360.0)
GARMIN_COM_URL_DICT = {
    "SSO_URL_ORIGIN": "https://sso.garmin.com",
    "SSO_URL": "https://sso.garmin.com/sso",
    "MODERN_URL": "https://connectapi.garmin.com",
    "SIGNIN_URL": "https://sso.garmin.com/sso/signin",
    "UPLOAD_URL": "https://connectapi.garmin.com/upload-service/upload/",
    "ACTIVITY_URL": "https://connectapi.garmin.com/activity-service/activity/{activity_id}",
}

GARMIN_CN_URL_DICT = {
    "SSO_URL_ORIGIN": "https://sso.garmin.com",
    "SSO_URL": "https://sso.garmin.cn/sso",
    "MODERN_URL": "https://connectapi.garmin.cn",
    "SIGNIN_URL": "https://sso.garmin.cn/sso/signin",
    "UPLOAD_URL": "https://connectapi.garmin.cn/upload-service/upload/",
    "ACTIVITY_URL": "https://connectapi.garmin.cn/activity-service/activity/{activity_id}",
}


class Garmin:
    def __init__(self, secret_string, auth_domain, is_only_running=True):
        """
        Init module
        """
        self.req = httpx.AsyncClient(timeout=TIME_OUT)
        self.cf_req = cloudscraper.CloudScraper()
        self.URL_DICT = (
            GARMIN_CN_URL_DICT
            if auth_domain and str(auth_domain).upper() == "CN"
            else GARMIN_COM_URL_DICT
        )
        garth.configure(domain="garmin.cn")
        self.modern_url = self.URL_DICT.get("MODERN_URL")
        secret_string = "W3sib2F1dGhfdG9rZW4iOiAiM2FjM2VkMWItYTYxMC00NmUwLWIyYWQtY2Q4MTBiMTMyZWFiIiwgIm9hdXRoX3Rva2VuX3NlY3JldCI6ICJiQ0RnQ2VRdVJ3MzZPd003SzlodVNMRkNNb0hYVU82MzNPcyIsICJtZmFfdG9rZW4iOiBudWxsLCAibWZhX2V4cGlyYXRpb25fdGltZXN0YW1wIjogbnVsbCwgImRvbWFpbiI6ICJnYXJtaW4uY24ifSwgeyJzY29wZSI6ICJDT01NVU5JVFlfQ09VUlNFX1JFQUQgR0FSTUlOUEFZX1dSSVRFIEdPTEZfQVBJX1JFQUQgQVRQX1JFQUQgR0hTX1NBTUQgR0hTX1VQTE9BRCBJTlNJR0hUU19SRUFEIENPTU1VTklUWV9DT1VSU0VfV1JJVEUgQ09OTkVDVF9XUklURSBHQ09GRkVSX1dSSVRFIEdBUk1JTlBBWV9SRUFEIERUX0NMSUVOVF9BTkFMWVRJQ1NfV1JJVEUgR09MRl9BUElfV1JJVEUgSU5TSUdIVFNfV1JJVEUgUFJPRFVDVF9TRUFSQ0hfUkVBRCBPTVRfQ0FNUEFJR05fUkVBRCBPTVRfU1VCU0NSSVBUSU9OX1JFQUQgR0NPRkZFUl9SRUFEIENPTk5FQ1RfUkVBRCBBVFBfV1JJVEUiLCAianRpIjogImMwZWNmYzJkLWYyNjItNDFiMS1hMGE0LTM1ZjUzNDQ5NTRhNCIsICJ0b2tlbl90eXBlIjogIkJlYXJlciIsICJhY2Nlc3NfdG9rZW4iOiAiZXlKaGJHY2lPaUpTVXpJMU5pSXNJblI1Y0NJNklrcFhWQ0lzSW10cFpDSTZJbVJwTFc5aGRYUm9MWE5wWjI1bGNpMXdjbTlrTFdOdU1TMHlNREkwTFhFeEluMC5leUp6WTI5d1pTSTZXeUpCVkZCZlVrVkJSQ0lzSWtGVVVGOVhVa2xVUlNJc0lrTlBUVTFWVGtsVVdWOURUMVZTVTBWZlVrVkJSQ0lzSWtOUFRVMVZUa2xVV1Y5RFQxVlNVMFZmVjFKSlZFVWlMQ0pEVDA1T1JVTlVYMUpGUVVRaUxDSkRUMDVPUlVOVVgxZFNTVlJGSWl3aVJGUmZRMHhKUlU1VVgwRk9RVXhaVkVsRFUxOVhVa2xVUlNJc0lrZEJVazFKVGxCQldWOVNSVUZFSWl3aVIwRlNUVWxPVUVGWlgxZFNTVlJGSWl3aVIwTlBSa1pGVWw5U1JVRkVJaXdpUjBOUFJrWkZVbDlYVWtsVVJTSXNJa2RJVTE5VFFVMUVJaXdpUjBoVFgxVlFURTlCUkNJc0lrZFBURVpmUVZCSlgxSkZRVVFpTENKSFQweEdYMEZRU1Y5WFVrbFVSU0lzSWtsT1UwbEhTRlJUWDFKRlFVUWlMQ0pKVGxOSlIwaFVVMTlYVWtsVVJTSXNJazlOVkY5RFFVMVFRVWxIVGw5U1JVRkVJaXdpVDAxVVgxTlZRbE5EVWtsUVZFbFBUbDlTUlVGRUlpd2lVRkpQUkZWRFZGOVRSVUZTUTBoZlVrVkJSQ0pkTENKcGMzTWlPaUpvZEhSd2N6b3ZMMlJwWVhWMGFDNW5ZWEp0YVc0dVkyNGlMQ0p5WlhadlkyRjBhVzl1WDJWc2FXZHBZbWxzYVhSNUlqcGJJa2RNVDBKQlRGOVRTVWRPVDFWVUlsMHNJbU5zYVdWdWRGOTBlWEJsSWpvaVZVNUVSVVpKVGtWRUlpd2laWGh3SWpveE56TXlOVEUyT0RZNExDSnBZWFFpT2pFM016STBNVE0yTURnc0ltZGhjbTFwYmw5bmRXbGtJam9pTm1aaE1tVTVZMlF0TkRaaU1DMDBNR0V3TFdGak1tTXRNalkwTnpObFltUmxZamMwSWl3aWFuUnBJam9pWXpCbFkyWmpNbVF0WmpJMk1pMDBNV0l4TFdFd1lUUXRNelZtTlRNME5EazFOR0UwSWl3aVkyeHBaVzUwWDJsa0lqb2lSMEZTVFVsT1gwTlBUazVGUTFSZlRVOUNTVXhGWDBGT1JGSlBTVVJmUkVraWZRLkFpUWZPUGs2eGwyckd4a3pINi1PNUpJWVpHTzdxeU1YOEhaMnpxandQeW5BZnhmb1NMYU9GMVE5TzNKUkhnOWFfWTBUOWdmX0w2SFhOTmRUTms5UFYyZnZQNGw4Vk5sX0hxMU11LUFDUGRwVGUwZm0tSkMtcVpTZG9ya1dtNzNjdHhIMENqRk9zZEFnTlhkYnFlNUVTZEpJZEhKVjFlWDI5eURzVy1sN1Brd2U4QnpkS0c4NVY2dUt4UU9tVkdsN3R2dU5Sel9UNlJhaXowVmttZ1FwMUlCTTdrTWZsWEp2TVNBWnpBODZtbUZMV1FjQWNCY2JNbjFxTkMwOGVMLVF0MlZiOWtibTY4Y0pNUFEtNkhidkJ2blprN3dRX2s2c2YyYldVWFpTVGh4UFM1dDlfS1BZQVRzM1FuY1FjX0ozaEZEcjVaRDFKTHZiVGdvSVZoSlZpQSIsICJyZWZyZXNoX3Rva2VuIjogImV5SnlaV1p5WlhOb1ZHOXJaVzVXWVd4MVpTSTZJalpoWXpnM1pHRmhMVEl5WlRJdE5EbGtZeTA0WmpSbExXSmpNR1V5TVRZME1UYzBZU0lzSW1kaGNtMXBia2QxYVdRaU9pSTJabUV5WlRsalpDMDBObUl3TFRRd1lUQXRZV015WXkweU5qUTNNMlZpWkdWaU56UWlmUT09IiwgImV4cGlyZXNfaW4iOiAxMDMyNTksICJleHBpcmVzX2F0IjogMTczMjUxNjg2NywgInJlZnJlc2hfdG9rZW5fZXhwaXJlc19pbiI6IDI1OTE5OTksICJyZWZyZXNoX3Rva2VuX2V4cGlyZXNfYXQiOiAxNzM1MDA1NjA3fV0="
        garth.client.loads(secret_string)
        if garth.client.oauth2_token.expired:
            garth.client.refresh_oauth2()

        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/79.0.3945.88 Safari/537.36",
            "origin": self.URL_DICT.get("SSO_URL_ORIGIN"),
            "nk": "NT",
            "Authorization": str(garth.client.oauth2_token),
        }
        self.is_only_running = is_only_running
        self.upload_url = self.URL_DICT.get("UPLOAD_URL")
        self.activity_url = self.URL_DICT.get("ACTIVITY_URL")

    async def fetch_data(self, url, retrying=False):
        """
        Fetch and return data
        """
        print("fetch_data ------------------ ")
        print(url)
        try:
            response = await self.req.get(url, headers=self.headers)
            if response.status_code == 429:
                raise GarminConnectTooManyRequestsError("Too many requests")
            logger.debug(f"fetch_data got response code {response.status_code}")
            response.raise_for_status()
            return response.json()
        except Exception as err:
            print(err)
            if retrying:
                logger.debug(
                    "Exception occurred during data retrieval, relogin without effect: %s"
                    % err
                )
                raise GarminConnectConnectionError("Error connecting") from err
            else:
                logger.debug(
                    "Exception occurred during data retrieval - perhaps session expired - trying relogin: %s"
                    % err
                )
                await self.fetch_data(url, retrying=True)

    async def get_activities(self, start, limit):
        """
        Fetch available activities
        """
        print(f"get_activities ------------------ {start} -- {limit}")
        url = f"https://connectapi.garmin.cn/activitylist-service/activities/search/activities?start={start}&limit={limit}"
        if self.is_only_running:
            url = url + "&activityType=running"
        return await self.fetch_data(url)

    async def download_activity(self, activity_id, file_type="gpx"):
        url = f"https://connectapi.garmin.cn/download-service/export/{file_type}/activity/{activity_id}"
        if file_type == "fit":
            url = f"https://connectapi.garmin.cn/download-service/files/activity/{activity_id}"
        logger.info(f"Download activity from {url}")
        response = await self.req.get(url, headers=self.headers)
        response.raise_for_status()
        return response.read()

    async def upload_activities_original_from_strava(
        self, datas, use_fake_garmin_device=False
    ):
        print(
            "start upload activities to garmin!, use_fake_garmin_device:",
            use_fake_garmin_device,
        )
        for data in datas:
            print(data.filename)
            with open(data.filename, "wb") as f:
                for chunk in data.content:
                    f.write(chunk)
            f = open(data.filename, "rb")
            # wrap fake garmin device to origin fit file, current not support gpx file
            if use_fake_garmin_device:
                file_body = wrap_device_info(f)
            else:
                file_body = BytesIO(f.read())
            files = {"file": (data.filename, file_body)}

            try:
                res = await self.req.post(
                    self.upload_url, files=files, headers=self.headers
                )
                os.remove(data.filename)
                f.close()
            except Exception as e:
                print(str(e))
                # just pass for now
                continue
            try:
                resp = res.json()["detailedImportResult"]
                print("garmin upload success: ", resp)
            except Exception as e:
                print("garmin upload failed: ", e)
        await self.req.aclose()

    async def upload_activity_from_file(self, file):
        print("Uploading " + str(file))
        f = open(file, "rb")

        file_body = BytesIO(f.read())
        files = {"file": (file, file_body)}

        try:
            res = await self.req.post(
                self.upload_url, files=files, headers=self.headers
            )
            f.close()
        except Exception as e:
            print(str(e))
            # just pass for now
            return
        try:
            resp = res.json()["detailedImportResult"]
            print("garmin upload success: ", resp)
        except Exception as e:
            print("garmin upload failed: ", e)

    async def upload_activities_files(self, files):
        print("start upload activities to garmin!")

        await gather_with_concurrency(
            10,
            [self.upload_activity_from_file(file=f) for f in files],
        )

        await self.req.aclose()


class GarminConnectHttpError(Exception):
    def __init__(self, status):
        super(GarminConnectHttpError, self).__init__(status)
        self.status = status


class GarminConnectConnectionError(Exception):
    """Raised when communication ended in error."""

    def __init__(self, status):
        """Initialize."""
        super(GarminConnectConnectionError, self).__init__(status)
        self.status = status


class GarminConnectTooManyRequestsError(Exception):
    """Raised when rate limit is exceeded."""

    def __init__(self, status):
        """Initialize."""
        super(GarminConnectTooManyRequestsError, self).__init__(status)
        self.status = status


class GarminConnectAuthenticationError(Exception):
    """Raised when login returns wrong result."""

    def __init__(self, status):
        """Initialize."""
        super(GarminConnectAuthenticationError, self).__init__(status)
        self.status = status


async def download_garmin_data(client, activity_id, file_type="gpx"):
    folder = FOLDER_DICT.get(file_type, "gpx")
    try:
        file_data = await client.download_activity(activity_id, file_type=file_type)
        file_path = os.path.join(folder, f"{activity_id}.{file_type}")
        need_unzip = False
        if file_type == "fit":
            file_path = os.path.join(folder, f"{activity_id}.zip")
            need_unzip = True
        async with aiofiles.open(file_path, "wb") as fb:
            await fb.write(file_data)
        if need_unzip:
            zip_file = zipfile.ZipFile(file_path, "r")
            for file_info in zip_file.infolist():
                zip_file.extract(file_info, folder)
                if file_info.filename.endswith(".fit"):
                    os.rename(
                        os.path.join(folder, f"{activity_id}_ACTIVITY.fit"),
                        os.path.join(folder, f"{activity_id}.fit"),
                    )
                elif file_info.filename.endswith(".gpx"):
                    os.rename(
                        os.path.join(folder, f"{activity_id}_ACTIVITY.gpx"),
                        os.path.join(FOLDER_DICT["gpx"], f"{activity_id}.gpx"),
                    )
                else:
                    os.remove(os.path.join(folder, file_info.filename))
            os.remove(file_path)
    except Exception as e:
        print(f"Failed to download activity {activity_id}: {str(e)}")
        traceback.print_exc()


async def get_activity_id_list(client, start=0):
    activities = await client.get_activities(start, 100)
    if len(activities) > 0:
        ids = list(map(lambda a: str(a.get("activityId", "")), activities))
        print(f"Syncing Activity IDs -- len(activities): {len(activities)}")
        print("--------------------------")
        return ids + await get_activity_id_list(client, start + 100)
    else:
        return []


async def gather_with_concurrency(n, tasks):
    semaphore = asyncio.Semaphore(n)

    async def sem_task(task):
        async with semaphore:
            return await task

    return await asyncio.gather(*(sem_task(task) for task in tasks))


def get_downloaded_ids(folder):
    return [i.split(".")[0] for i in os.listdir(folder) if not i.startswith(".")]


async def download_new_activities(
    secret_string, auth_domain, downloaded_ids, is_only_running, folder, file_type
):
    client = Garmin(secret_string, auth_domain, is_only_running)
    # because I don't find a para for after time, so I use garmin-id as filename
    # to find new run to generage
    activity_ids = await get_activity_id_list(client)
    print(
        f"--- download_new_activities ------------ after get_activity_id_list ------ {len(activity_ids)}"
    )
    to_generate_garmin_ids = list(set(activity_ids) - set(downloaded_ids))
    print(f"{len(to_generate_garmin_ids)} new activities to be downloaded")

    start_time = time.time()
    await gather_with_concurrency(
        10,
        [
            download_garmin_data(client, id, file_type=file_type)
            for id in to_generate_garmin_ids
        ],
    )
    print(f"Download finished. Elapsed {time.time()-start_time} seconds")

    await client.req.aclose()
    return to_generate_garmin_ids


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "secret_string", nargs="?", help="secret_string fro get_garmin_secret.py"
    )
    parser.add_argument(
        "--is-cn",
        dest="is_cn",
        action="store_true",
        help="if garmin accout is cn",
    )
    parser.add_argument(
        "--only-run",
        dest="only_run",
        action="store_true",
        help="if is only for running",
    )
    parser.add_argument(
        "--tcx",
        dest="download_file_type",
        action="store_const",
        const="tcx",
        default="gpx",
        help="to download personal documents or ebook",
    )
    parser.add_argument(
        "--fit",
        dest="download_file_type",
        action="store_const",
        const="fit",
        default="gpx",
        help="to download personal documents or ebook",
    )
    options = parser.parse_args()
    secret_string = options.secret_string
    print("--------------------------------------------------")
    print(os.getenv("GARMIN_SECRET_STRING"))
    auth_domain = (
        "CN" if options.is_cn else config("sync", "garmin", "authentication_domain")
    )
    file_type = options.download_file_type
    is_only_running = options.only_run
    print(auth_domain)
    secret_string = "W3sib2F1dGhfdG9rZW4iOiAiM2FjM2VkMWItYTYxMC00NmUwLWIyYWQtY2Q4MTBiMTMyZWFiIiwgIm9hdXRoX3Rva2VuX3NlY3JldCI6ICJiQ0RnQ2VRdVJ3MzZPd003SzlodVNMRkNNb0hYVU82MzNPcyIsICJtZmFfdG9rZW4iOiBudWxsLCAibWZhX2V4cGlyYXRpb25fdGltZXN0YW1wIjogbnVsbCwgImRvbWFpbiI6ICJnYXJtaW4uY24ifSwgeyJzY29wZSI6ICJDT01NVU5JVFlfQ09VUlNFX1JFQUQgR0FSTUlOUEFZX1dSSVRFIEdPTEZfQVBJX1JFQUQgQVRQX1JFQUQgR0hTX1NBTUQgR0hTX1VQTE9BRCBJTlNJR0hUU19SRUFEIENPTU1VTklUWV9DT1VSU0VfV1JJVEUgQ09OTkVDVF9XUklURSBHQ09GRkVSX1dSSVRFIEdBUk1JTlBBWV9SRUFEIERUX0NMSUVOVF9BTkFMWVRJQ1NfV1JJVEUgR09MRl9BUElfV1JJVEUgSU5TSUdIVFNfV1JJVEUgUFJPRFVDVF9TRUFSQ0hfUkVBRCBPTVRfQ0FNUEFJR05fUkVBRCBPTVRfU1VCU0NSSVBUSU9OX1JFQUQgR0NPRkZFUl9SRUFEIENPTk5FQ1RfUkVBRCBBVFBfV1JJVEUiLCAianRpIjogImMwZWNmYzJkLWYyNjItNDFiMS1hMGE0LTM1ZjUzNDQ5NTRhNCIsICJ0b2tlbl90eXBlIjogIkJlYXJlciIsICJhY2Nlc3NfdG9rZW4iOiAiZXlKaGJHY2lPaUpTVXpJMU5pSXNJblI1Y0NJNklrcFhWQ0lzSW10cFpDSTZJbVJwTFc5aGRYUm9MWE5wWjI1bGNpMXdjbTlrTFdOdU1TMHlNREkwTFhFeEluMC5leUp6WTI5d1pTSTZXeUpCVkZCZlVrVkJSQ0lzSWtGVVVGOVhVa2xVUlNJc0lrTlBUVTFWVGtsVVdWOURUMVZTVTBWZlVrVkJSQ0lzSWtOUFRVMVZUa2xVV1Y5RFQxVlNVMFZmVjFKSlZFVWlMQ0pEVDA1T1JVTlVYMUpGUVVRaUxDSkRUMDVPUlVOVVgxZFNTVlJGSWl3aVJGUmZRMHhKUlU1VVgwRk9RVXhaVkVsRFUxOVhVa2xVUlNJc0lrZEJVazFKVGxCQldWOVNSVUZFSWl3aVIwRlNUVWxPVUVGWlgxZFNTVlJGSWl3aVIwTlBSa1pGVWw5U1JVRkVJaXdpUjBOUFJrWkZVbDlYVWtsVVJTSXNJa2RJVTE5VFFVMUVJaXdpUjBoVFgxVlFURTlCUkNJc0lrZFBURVpmUVZCSlgxSkZRVVFpTENKSFQweEdYMEZRU1Y5WFVrbFVSU0lzSWtsT1UwbEhTRlJUWDFKRlFVUWlMQ0pKVGxOSlIwaFVVMTlYVWtsVVJTSXNJazlOVkY5RFFVMVFRVWxIVGw5U1JVRkVJaXdpVDAxVVgxTlZRbE5EVWtsUVZFbFBUbDlTUlVGRUlpd2lVRkpQUkZWRFZGOVRSVUZTUTBoZlVrVkJSQ0pkTENKcGMzTWlPaUpvZEhSd2N6b3ZMMlJwWVhWMGFDNW5ZWEp0YVc0dVkyNGlMQ0p5WlhadlkyRjBhVzl1WDJWc2FXZHBZbWxzYVhSNUlqcGJJa2RNVDBKQlRGOVRTVWRPVDFWVUlsMHNJbU5zYVdWdWRGOTBlWEJsSWpvaVZVNUVSVVpKVGtWRUlpd2laWGh3SWpveE56TXlOVEUyT0RZNExDSnBZWFFpT2pFM016STBNVE0yTURnc0ltZGhjbTFwYmw5bmRXbGtJam9pTm1aaE1tVTVZMlF0TkRaaU1DMDBNR0V3TFdGak1tTXRNalkwTnpObFltUmxZamMwSWl3aWFuUnBJam9pWXpCbFkyWmpNbVF0WmpJMk1pMDBNV0l4TFdFd1lUUXRNelZtTlRNME5EazFOR0UwSWl3aVkyeHBaVzUwWDJsa0lqb2lSMEZTVFVsT1gwTlBUazVGUTFSZlRVOUNTVXhGWDBGT1JGSlBTVVJmUkVraWZRLkFpUWZPUGs2eGwyckd4a3pINi1PNUpJWVpHTzdxeU1YOEhaMnpxandQeW5BZnhmb1NMYU9GMVE5TzNKUkhnOWFfWTBUOWdmX0w2SFhOTmRUTms5UFYyZnZQNGw4Vk5sX0hxMU11LUFDUGRwVGUwZm0tSkMtcVpTZG9ya1dtNzNjdHhIMENqRk9zZEFnTlhkYnFlNUVTZEpJZEhKVjFlWDI5eURzVy1sN1Brd2U4QnpkS0c4NVY2dUt4UU9tVkdsN3R2dU5Sel9UNlJhaXowVmttZ1FwMUlCTTdrTWZsWEp2TVNBWnpBODZtbUZMV1FjQWNCY2JNbjFxTkMwOGVMLVF0MlZiOWtibTY4Y0pNUFEtNkhidkJ2blprN3dRX2s2c2YyYldVWFpTVGh4UFM1dDlfS1BZQVRzM1FuY1FjX0ozaEZEcjVaRDFKTHZiVGdvSVZoSlZpQSIsICJyZWZyZXNoX3Rva2VuIjogImV5SnlaV1p5WlhOb1ZHOXJaVzVXWVd4MVpTSTZJalpoWXpnM1pHRmhMVEl5WlRJdE5EbGtZeTA0WmpSbExXSmpNR1V5TVRZME1UYzBZU0lzSW1kaGNtMXBia2QxYVdRaU9pSTJabUV5WlRsalpDMDBObUl3TFRRd1lUQXRZV015WXkweU5qUTNNMlZpWkdWaU56UWlmUT09IiwgImV4cGlyZXNfaW4iOiAxMDMyNTksICJleHBpcmVzX2F0IjogMTczMjUxNjg2NywgInJlZnJlc2hfdG9rZW5fZXhwaXJlc19pbiI6IDI1OTE5OTksICJyZWZyZXNoX3Rva2VuX2V4cGlyZXNfYXQiOiAxNzM1MDA1NjA3fV0="
    if secret_string is None and os.getenv("GARMIN_SECRET_STRING") is not None:
        secret_string = os.getenv("GARMIN_SECRET_STRING")
    if secret_string is None:
        print("Missing argument nor valid configuration file for Garmin")
        sys.exit(1)
    folder = FOLDER_DICT.get(file_type, "gpx")
    # make gpx or tcx dir
    if not os.path.exists(folder):
        os.mkdir(folder)
    downloaded_ids = get_downloaded_ids(folder)

    loop = asyncio.get_event_loop()
    future = asyncio.ensure_future(
        download_new_activities(
            secret_string,
            auth_domain,
            downloaded_ids,
            is_only_running,
            folder,
            file_type,
        )
    )
    loop.run_until_complete(future)
    # fit may contain gpx(maybe upload by user)
    if file_type == "fit":
        make_activities_file(SQL_FILE, FOLDER_DICT["gpx"], JSON_FILE, file_suffix="gpx")
    make_activities_file(SQL_FILE, folder, JSON_FILE, file_suffix=file_type)
