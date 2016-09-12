import os
import json
import time
import datetime
import requests
import logging

from redo import retry

headers = {
    'Accept': 'application/json',
    'User-Agent': 'ouija',
}
logger = logging.getLogger(__name__)
TREEHERDER_HOST = "https://treeherder.mozilla.org/api/project/{0}/" \
                  "runnable_jobs/?decisionTaskID={1}&format=json"

def get_rootdir():

    path = os.path.expanduser('~/.mozilla/seta/')
    if not os.path.exists(path):
        os.makedirs(path)

    return path


# TODO we need add test for this function to make sure it works under any situation
def update_runnableapi():
    """Use it to update runnablejobs.json file."""
    url = "https://index.taskcluster.net/v1/task/gecko.v2.%s.latest.firefox.decision/"
    try:
        latest_task = retry(requests.get, args=(url % "mozilla-inbound", ),
                            kwargs={'headers': {'accept-encoding': 'json'},
                                    'verify': True}).json()
    except Exception as error:
        # we will end this function if got exception here
        logger.debug("the request to %s failed, due to %s" % (url, error))
        return
    task_id = latest_task['taskId']

    # The format of expires is like 2017-07-04T22:13:23.248Z and we only want 2017-07-04 part
    expires = latest_task['expires'].split('T')[0]
    time_tuple = datetime.datetime.strptime(expires, "%Y-%m-%d").timetuple()
    new_timestamp = time.mktime(time_tuple)
    path = get_rootdir() + '/runnablejobs.json'

    # we do nothing if the timestamp of runablejobs.json is equal with the latest task
    # otherwise we download and update it
    if os.path.isfile(path):
        with open(path, 'r') as data:
            # read the timesstamp of this task from json file
            oldtime = json.loads(data.read())['meta']['timetamp']
        if oldtime == new_timestamp:
            print "The runnable json file is latest already."
            return
        else:
            print "It's going to update your runnable jobs data."
            data = query_the_runnablejobs(new_timestamp, task_id)
            add_new_jobs_into_pressed(new_data=data)
            with open(path, 'w') as f:
                json.dump(data, f)
    else:
        print "It's going to help you download the runnable jobs file."
        data = query_the_runnablejobs(new_timestamp, task_id)
        if data:
            with open(path, 'w') as f:
                json.dump(data, f)


def query_the_runnablejobs(new_timestamp, task_id=None):
    if task_id:
        url = TREEHERDER_HOST.format('mozilla-inbound', task_id)
        try:
            data = retry(requests.get, args=(url, ), kwargs={'headers': headers}).json()
            if len(data['results']) > 0:
                data['meta'].update({'timetamp': new_timestamp})
        except:
            print "failed to get runnablejobs via %s" % url
            print "We have something wrong with the runnable api, switch to the old runnablejobs.json now"
            with open(get_rootdir() + '/runnablejobs.json', 'r') as data:
                data = json.loads(data.read())
        return data


def add_new_jobs_into_pressed(new_data=None):
    if new_data:
        with open(get_rootdir() + '/runnablejobs.json', 'r') as f:
            old_data = json.loads(f.read())['results']

        with open(get_rootdir() + '/src/preseed.json', 'r') as f:
            preseed_jobs = json.loads(f.read())

        # If a job in recent runnablejobs and can't been found in the old runnablejobs,
        # that job been determined as a new job and pick it up.
        new_jobs = [new_job for new_job in new_data['results']
                    if new_job not in old_data]
        if len(new_jobs) > 0:
            for job in new_jobs:
                # This part of code is actually duplicate with jobtypes.
                if job['build_system_type'] == 'buildbot':
                    testtype = job['ref_data_name'].split(' ')[-1]
                else:
                    if job['ref_data_name'].startswith('desktop-test') or \
                            job['ref_data_name'].startswith('android-test'):
                        separator = job['platform_option'] if \
                            job['platform_option'] != 'asan' else 'opt'
                        testtype = job['job_type_name'].split(
                            '{buildtype}-'.format(buildtype=separator))[-1]

                    else:
                        continue
                for j in preseed_jobs:
                    # If the job had already in there, we just keep it.
                    if (j['name'] == testtype and
                            j['platform'] == job["build_platform"] and
                            j['buildtype'] == job["platform_option"]):
                        continue

                    else:
                        expires = (datetime.date.today() +
                                   datetime.timedelta(days=14)).strftime('%Y-%m-%d')

                        temp = {"platform": job["build_platform"],
                                "buildtype": job["platform_option"],
                                "name": testtype,
                                "expires": expires,
                                "action": "run"}
                        if temp not in preseed_jobs:
                            preseed_jobs.append(temp)

            with open(get_rootdir() + '/src/preseed.json', 'w+') as f:
                json.dump(preseed_jobs, f)

if __name__ == "__main__":
    update_runnableapi()