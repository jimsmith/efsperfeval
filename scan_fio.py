import argparse
import json
import os
import random
import re
import uuid
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

def gen_job(job_file_name, test_path, block_size, rw_mode, io_depth,
        warmup_time, run_time):
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
            "\n"
            "[file1]\n"
            "size=1G\n"
            "ioengine=libaio\n"
            "iodepth=%d\n")
        f.write(config_template % (test_path, rw_mode, block_size, run_time, io_depth))

if __name__=="__main__":
    parser = argparse.ArgumentParser(description="Evaluate a file system")
    parser.add_argument('result', help='output directory for results')
    parser.add_argument('--fio-command', default='/usr/local/bin/fio',
                        help='path to the fio executable')
    parser.add_argument('--block-sizes', default='4K,32K',
                        help='number of test fio clients')
    parser.add_argument('--test-paths', required=True,
                        help='paths under test')
    parser.add_argument('--modes', default='randread',
                        help='paths under test')
    parser.add_argument('--num-clients', default='1',
                        help='number of test fio clients')
    parser.add_argument('--num-iterations', type=int, default=1,
                        help='number of test fio clients')
    args = parser.parse_args()

    if not os.path.isdir(args.result):
        print("result must be a directory")
        sys.exit(1)

    def splitstrings(arg_str):
        return [x.strip() for x in arg_str.split(",")]
    test_block_sizes = list(splitstrings(args.num_clients))
    test_clients = list([int(x) for x in splitstrings(args.num_clients)])
    test_paths = list(splitstrings(args.test_paths))
    test_modes = list(splitstrings(args.modes))
    num_iterations = args.num_iterations

    supported_modes = ["read","write","randread","randwrite","randrw"]
    for mode in test_modes:
        if mode not in supported_modes:
            print("%s is not a supported mode" % mode)
            sys.exit(1)

    invocation_id = '%016x' % random.getrandbits(64)
    scan_configuration = {
        "invocation_id": invocation_id,
        "paths": test_paths,
        'block_sizes': test_block_sizes,
        'modes': test_modes,
        'clients': test_clients,
        'iterations': num_iterations
    }
    print(scan_configuration)
    sys.exit(0)
    for i in range(num_iterations):
        for test_path in test_paths:
            for bs in test_block_sizes:
                for rw_mode in test_modes:
                    for c in test_clients:
                        experiment_id = uuid.uuid4()
                        print("experiment %s" % experiment_id)
                        host_list_fn = os.path.join(args.result, "%s.host.list" % experiment_id)
                        gen_host_list(host_list_fn, 'host.list', c)
                        job_fn = os.path.join(args.result, "%s.job" % experiment_id)
                        gen_job(job_fn, test_path, bs, rw_mode, 8, 0, 3)
                        experiment_config = {
                            "mount_path": test_path,
                            "block_size": bs,
                            "mode": rw_mode,
                            "concurrency": c,
                            "invocation_id": invocation_id,
                            "iteration": i
                        }
                        print("running", experiment_config)
                        start_time = time.time()
                        p = subprocess.Popen([args.fio_command,
                            "--client=%s" % host_list_fn,
                            "--output-format=json",
                            job_fn],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                        fio_stdout, fio_stderr = p.communicate()
                        end_time = time.time()
                        if p.returncode:
                            print("fio failed")
                            print(fio_stderr)
                        else:
                            print("result string", fio_stdout.decode("utf-8"))
                            m = re.search("\{.*\}", fio_stdout.decode("utf-8"), re.MULTILINE | re.DOTALL)
                            experiment_output = experiment_config
                            experiment_output["start_time"] = start_time
                            experiment_output["end_time"] = end_time
                            if not m:
                                experiment_output["success"] = False
                                experiment_output["fio_stdout"] = fio_stdout
                                experiment_output["fio_stderr"] = fio_stderr
                            else:
                                experiment_output["fio_output"] = json.loads(m.group(0))
                            with open(os.path.join(args.result, "%s.json" % experiment_id),"w") as f:
                                json.dump(experiment_output, f)
                        cleanup([job_fn, host_list_fn])
