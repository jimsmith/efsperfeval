import argparse
import json
import os
import random
import re
import subprocess
import sys
import time

def gen_host_list(host_list_fn, host_list_source_fn, num_hosts):
    with open(host_list_source_fn,"r") as fin:
        all_hosts = list(fin.readlines())
    if len(all_hosts) < num_hosts:
        raise RuntimeError("insufficient number of hosts")
    with open(host_list_fn,"w") as fout:
        for host in all_hosts[:num_hosts]:
            fout.write(host)

def cleanup(file_names):
    for fn in file_names:
        os.unlink(fn)

def gen_job(job_file_name, test_path, unique_filenames, files_per_client,
        block_size, rw_mode,
        io_depth, ramp_time, run_time):
    with open(job_file_name,"w") as f:
        config_template = ("[global]\n"
            "name=fio-scan-file\n"
            "directory=%s\n"
            "filename=fio-test-1g\n"
            "rw=%s\n"
            "bs=%s\n"
            "direct=1\n"
            "numjobs=1\n"
            "time_based=1\n"
            "runtime=%d\n"
            "ramp_time=%d\n"
            "unique_filename=%d\n"
            "nrfiles=%d\n"
            "\n"
            "[file1]\n"
            "size=1G\n"
            "ioengine=libaio\n"
            "iodepth=%d\n")
        f.write(config_template % (test_path, rw_mode, block_size, run_time,
            ramp_time, 1 if unique_filenames else 0, files_per_client, io_depth))

def run_fio(host_list_fn, job_fn):
    fio_args = [args.fio_command,
        "--client=%s" % host_list_fn,
        "--output-format=json",
        job_fn]
    print("executing", " ".join(fio_args))
    p = subprocess.Popen(fio_args,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    fio_stdout, fio_stderr = p.communicate()
    if p.returncode:
        print("fio failed")
        print(fio_stdout)
        print(fio_stderr)
        raise
    else:
        m = re.search("\{.*\}", fio_stdout.decode("utf-8"), re.MULTILINE | re.DOTALL)
        if not m:
            print("failed to find json in fio output")
            print(fio_stdout)
            print(fio_stderr)
            raise
        else:
            return json.loads(m.group(0))

if __name__=="__main__":
    parser = argparse.ArgumentParser(description="Evaluate a file system")
    parser.add_argument("--results", required=True,
                        help="output directory for results")
    parser.add_argument("--fio-command", default="/usr/local/bin/fio",
                        help="path to the fio executable")
    parser.add_argument("--block-sizes", default="4K,32K",
                        help="number of test fio clients")
    parser.add_argument("--test-paths", default="/efs",
                        help="paths under test")
    parser.add_argument("--modes", default="randread",
                        help="paths under test")
    parser.add_argument("--num-clients", default="1",
                        help="number of test fio clients")
    parser.add_argument("--io-depths", default="8",
                        help="number of concurrent requests per client")
    parser.add_argument("--num-iterations", type=int, default=1,
                        help="number of test fio clients")
    parser.add_argument("--ramp-time", type=int, default=0,
                        help="warmup time before recording performance")
    parser.add_argument("--run-time", type=int, default=30,
                        help="time to run performance test")
    parser.add_argument("--unique-filenames", action="store_true",
                        help="use unique filenames at each client")
    parser.add_argument("--num-files-per-client", default="1",
                        help="number of files for each client")
    args = parser.parse_args()

    if not os.path.isdir(args.results):
        print("result must be a directory")
        sys.exit(1)

    def splitstrings(arg_str):
        return [x.strip() for x in arg_str.split(",")]
    test_block_sizes = list(splitstrings(args.block_sizes))
    test_clients = list([int(x) for x in splitstrings(args.num_clients)])
    test_paths = list(splitstrings(args.test_paths))
    test_modes = list(splitstrings(args.modes))
    test_io_depths = list([int(x) for x in splitstrings(args.io_depths)])
    num_iterations = args.num_iterations
    ramp_time = args.ramp_time
    run_time = args.run_time
    unique_filenames = args.unique_filenames
    test_files_per_client = list([int(x) for x in splitstrings(args.num_files_per_client)])

    supported_modes = ["read","write","randread","randwrite","randrw"]
    for mode in test_modes:
        if mode not in supported_modes:
            print("%s is not a supported mode" % mode)
            sys.exit(1)

    scan_invocation_id = "%016x" % random.getrandbits(64)
    scan_configuration = {
        "scan_invocation_id": scan_invocation_id,
        "paths": test_paths,
        "block_sizes": test_block_sizes,
        "modes": test_modes,
        "clients": test_clients,
        "io_depths": test_io_depths,
        "iterations": num_iterations,
        "unique_filenames": unique_filenames,
        "files_per_client": test_files_per_client,
        "ramp_time": ramp_time,
        "run_time": run_time
    }
    with open(os.path.join(args.results, "scan-%s.json" % scan_invocation_id), "w") as f:
        json.dump(scan_configuration, f)
    print("scan configuration", scan_configuration)

    # run a preparatory job to create any work files
    print("preparing test files")
    prep_host_list_fn = os.path.join(args.results, "%s-prep.host.list" % scan_invocation_id)
    gen_host_list(prep_host_list_fn, "host.list.private", max(test_clients))
    prep_job_fn = os.path.join(args.results, "%s-prep.job" % scan_invocation_id)
    for test_path in test_paths:
        gen_job(prep_job_fn, test_path, unique_filenames, max(test_files_per_client),
            "4k", "read", 1, 0, 1)
    run_fio(prep_host_list_fn, prep_job_fn)
    print("finished preparing test files")

    num_jobs = (num_iterations * len(test_paths) * len(test_block_sizes)
        * len(test_modes) * len(test_clients) * len(test_io_depths))
    job_ct = 0
    for i in range(1, num_iterations + 1):
        for test_path in test_paths:
            for bs in test_block_sizes:
                for rw_mode in test_modes:
                    for num_clients in test_clients:
                        for io_depth in test_io_depths:
                            for files_per_client in test_files_per_client:
                                job_ct += 1
                                experiment_id = "%016x" % random.getrandbits(64)
                                print("%d/%d: experiment %s" % (job_ct, num_jobs, experiment_id))
                                host_list_fn = os.path.join(args.results, "%s-%s.host.list" % (scan_invocation_id, experiment_id))
                                gen_host_list(host_list_fn, "host.list.private", num_clients)
                                job_fn = os.path.join(args.results, "%s-%s.job" % (scan_invocation_id, experiment_id))
                                gen_job(job_fn, test_path, unique_filenames, files_per_client, bs, rw_mode, io_depth, ramp_time, run_time)
                                experiment_config = {
                                    "mount_path": test_path,
                                    "unique_filenames": unique_filenames,
                                    "files_per_client": files_per_client,
                                    "block_size": bs,
                                    "mode": rw_mode,
                                    "clients": num_clients,
                                    "io_depth": io_depth,
                                    "ramp_time": ramp_time,
                                    "run_time": run_time,
                                    "scan_invocation_id": scan_invocation_id,
                                    "iteration": i
                                }
                                print("running", experiment_config)
                                start_time = time.time()
                                fio_output = run_fio(host_list_fn, job_fn)
                                end_time = time.time()
                                experiment_output = experiment_config
                                experiment_output["start_time"] = start_time
                                experiment_output["end_time"] = end_time
                                if fio_output:
                                    experiment_output["success"] = True
                                    experiment_output["fio_output"] = fio_output
                                else:
                                    experiment_output["success"] = False
                                with open(os.path.join(args.results, "%s-%s.json" % (scan_invocation_id, experiment_id)),"w") as f:
                                    json.dump(experiment_output, f)
                                cleanup([job_fn, host_list_fn])
    print("completed scan %s" % scan_invocation_id)
