import os as OS
import subprocess
import sys
import json
import urllib
try:
    import httplib2
except:
    subprocess.check_call(
        [sys.executable, "-m", "pip", "install", "httplib2"])
    import httplib2
try:
    import requests
except ImportError:
    subprocess.check_call(
        [sys.executable, "-m", "pip", "install", "requests"])
    import requests
import argparse
import find_rerun_job
import get_jenkins_params
import merge_reports

host = '172.23.121.84'
bucket_name = 'rerun_jobs'
TIMEOUT = 60


def parse_args():
    """
    Parse command line arguments into a dictionary
    @return: Dictionary of parsed command line arguments
    @rtype: dict
    """
    argument_parser = argparse.ArgumentParser()
    argument_parser.add_argument("build_version", type=str,
                                 help="Couchbase build version of the "
                                      "job")
    argument_parser.add_argument("--executor_jenkins_job",
                                 action='store_true',
                                 help="Run with current executor job")
    argument_parser.add_argument("--jenkins_job", action="store_true",
                                 help="Run with current jenkins job")
    argument_parser.add_argument("--install_failure",
                                 action='store_true',
                                 help="Was there install failure in "
                                      "the run?")
    argument_parser.add_argument("--manual_run", action="store_true",
                                 help="Is this a manual rerun of the "
                                      "job")
    args = vars(argument_parser.parse_args())
    return args


def build_args(build_version, executor_jenkins_job=False,
               jenkins_job=False, install_failure=False):
    """
    Build a dictionary of arguments needed for the program
    @param build_version: Couchbase build version of the job
    @type build_version: str
    @param executor_jenkins_job: Run with current Executor job
    @type executor_jenkins_job: bool
    @param jenkins_job: Run with current jenkins job
    @type jenkins_job: bool
    @param install_failure: Was there install failure in the run?
    @type install_failure: bool
    @return: Dictionary of parameters
    @rtype: dict
    """
    return locals()


def merge_xmls(rerun_document):
    print "Merging xmls"
    num_runs = rerun_document['num_runs'] - 1
    valid_run = False
    job = None
    while not valid_run and num_runs > 0:
        job = rerun_document['jobs'][num_runs - 1]
        if job['install_failure']:
            num_runs -= 1
        else:
            valid_run = True
    if not job:
        print "no valid jobs found with run results"
        testsuites = merge_reports.merge_reports("logs/**/*.xml")
        return testsuites
    job_url = job['job_url']
    artifacts = get_jenkins_params.get_js(job_url, "tree=artifacts[*]")
    if not artifacts or len(artifacts['artifacts']) == 0:
        print "could not find the job. Job might be deleted"
        testsuites = merge_reports.merge_reports("logs/**/*.xml")
        return testsuites
    relative_paths = []
    for artifact in artifacts["artifacts"]:
        if artifact["relativePath"].startswith("logs/") and \
                artifact["relativePath"].endswith(".xml"):
            relative_paths.append(artifact["relativePath"])
    logs = []
    for rel_path in relative_paths:
        xml_data = get_jenkins_params.download_url_data("{0}"
                                                        "{1}".format(
            job_url, rel_path))
        try:
            file_name = rel_path.split('/')[-1]
            file_name = "Old_Report_{0}.xml".format(file_name)
            f = open(file_name, "w")
            f.writelines(xml_data)
            f.close()
            logs.append(file_name)
        except Exception as e:
            print e
    logs.append("logs/**/*.xml")
    testsuites = merge_reports.merge_reports(logs)
    print "merged xmls"
    return testsuites


def should_rerun_tests(testsuites=None, install_failure=False,
                       retries=0):
    fresh_run = OS.getenv("fresh_run", False)
    if fresh_run == "true" or fresh_run is True:
        return False
    if install_failure and retries > 0:
        return True
    if retries < 1:
        return False
    should_rerun = False
    for tskey in testsuites.keys():
        tests = testsuites[tskey]['tests']
        for testname in tests.keys():
            testcase = tests[testname]
            errors = testcase['error']
            if errors:
                should_rerun = True
                break
        if should_rerun:
            break
    return should_rerun


def get_rerun_parameters(rerun_document=None, is_rerun=False):
    rerun_params = None
    if not is_rerun and not rerun_document or (rerun_document and
                                               rerun_document['num_runs'] == 1):
        current_job_url = OS.getenv("BUILD_URL")
        rerun_params = "-d failed={}".format(current_job_url)
    num_runs = rerun_document['num_runs']
    valid_run = False
    valid_job = None
    while not valid_run and num_runs > 0:
        job = rerun_document['jobs'][num_runs - 1]
        if job['install_failure']:
            num_runs -= 1
        else:
            valid_run = True
            valid_job = job
    if valid_run and valid_job:
        job_url = valid_job['job_url']
        rerun_params = "-d failed={}".format(job_url)
    return rerun_params


def run_jenkins_job(url, params):
    url = "{0}&{1}".format(url, urllib.urlencode(params))
    print url
    response, content = httplib2.Http(timeout=TIMEOUT).request(url,
                                                               'GET')
    return response, content


def rerun_job(args):
    build_version = args['build_version']
    executor_jenkins_job = args['executor_jenkins_job']
    jenkins_job = args['jenkins_job']
    install_failure = args['install_failure']
    fresh_run = OS.getenv('fresh_run', False)
    is_rerun_args = find_rerun_job.build_args(build_version,
                                              executor_jenkins_job=executor_jenkins_job,
                                              jenkins_job=jenkins_job,
                                              store_data=True,
                                              install_failure=install_failure)
    is_rerun, rerun_document = find_rerun_job.find_rerun_job(is_rerun_args)
    test_suites = {}
    if is_rerun and not install_failure and (fresh_run != 'true' or
                                             fresh_run is False):
        test_suites = merge_xmls(rerun_document)
    retry_count = OS.getenv("retries")
    if not retry_count:
        if "retries" in args:
            retry_count = args['retries']
        else:
            retry_count = 0
    if isinstance(retry_count, str):
        retry_count = int(retry_count)
    should_rerun = should_rerun_tests(test_suites, install_failure,
                                      retry_count)
    if not should_rerun:
        print "No more failed tests. Stopping reruns"
        return
    rerun_params = get_rerun_parameters(rerun_document, is_rerun)
    if not rerun_params:
        return
    if jenkins_job:
        current_job_url = OS.getenv('BUILD_URL')
        current_job_params = get_jenkins_params.get_params(
            current_job_url)
        current_job_params['rerun_params'] = rerun_params
        current_job_params['retries'] = retry_count - 1
        job_url = OS.getenv("JOB_URL")
        job_token = args['token']
        job_url = "{0}buildWithParameters?token={1}".format(job_url,
                                                          job_token)
        response, content = run_jenkins_job(job_url, current_job_params)
        return
    dispatcher_params = OS.getenv('dispatcher_params').lstrip(
        "parameters=")
    dispatcher_params = json.loads(dispatcher_params)
    dispatcher_params['rerun_params'] = rerun_params
    dispatcher_params['retries'] = retry_count - 1
    dispatcher_params['component'] = OS.getenv('component')
    dispatcher_params['subcomponent'] = OS.getenv('subcomponent')
    dispatcher_params['fresh_run'] = "false"
    job_url = dispatcher_params.pop('dispatcher_url')
    job_url = "{0}buildWithParameters?token=extended_sanity".format(
        job_url)
    response, content = run_jenkins_job(job_url, dispatcher_params)


def manual_rerun(args):
    build_version = args['build_version']
    executor_jenkins_job = args['executor_jenkins_job']
    jenkins_job = args['jenkins_job']
    is_rerun_args = find_rerun_job.build_args(build_version,
                                              executor_jenkins_job=executor_jenkins_job,
                                              jenkins_job=jenkins_job,
                                              store_data=False,
                                              install_failure=False)
    is_rerun, rerun_document = find_rerun_job.find_rerun_job(
        is_rerun_args)
    if not is_rerun:
        print "This is the first run for this build."
        return
    rerun_param = get_rerun_parameters(rerun_document, is_rerun)
    if not rerun_param:
        print "Could not find a valid previous build to run with"
        return
    with open("rerun_props_file", 'w') as f:
        to_write = "rerun_params_manual={}".format(
            rerun_param)
        f.write(to_write)
        f.close()


if __name__ == '__main__':
    args = parse_args()
    if args['manual_run']:
        manual_rerun(args)
    else:
        rerun_job(args)