import argparse
import os
import re
# import fnmatch
import json
# import os
# import re


def analyze_scan(results_path, scan_desc_fn, max_missing):
    with open(os.path.join(results_path, scan_desc_fn)) as f:
        scan_desc = json.load(f)
    res_filter = re.compile("%s-[0-9a-f]{16}\.json" % scan_desc["scan_invocation_id"])
    for fn in [f for f in os.listdir(results_path) if res_filter.match(f)]:
        # print(fn)
        with open(os.path.join(results_path, fn)) as f:
            data = json.load(f)
        if "success" in data and not data["success"]:
            raise
        # print(data["fio_output"].keys())
        client_stats = {}
        for cs in data["fio_output"]["client_stats"]:
            hostname = cs["hostname"]
            if hostname not in client_stats:
                client_stats[hostname] = cs

        # print(job_result)
        num_clients = len(client_stats)
        found_num_clients = False
        delta = 0
        while not found_num_clients and delta <= max_missing:
            if num_clients + delta in scan_desc["clients"]:
                found_num_clients = True
            delta += 1
        if not found_num_clients:
            print("invalid number of clients %d" % num_clients)
            continue
        client_read_iops = list([cs["read"]["iops_mean"] for cs in client_stats.values()])
        total_read_iops = sum(client_read_iops)
        client_read_latencies = list([cs["read"]["clat_ns"]["mean"] for cs in client_stats.values()])
        avg_read_latency = sum(client_read_latencies) / len(client_read_latencies)
        client_write_iops = list([cs["write"]["iops_mean"] for cs in client_stats.values()])
        total_write_iops = sum(client_write_iops)
        client_write_latencies = list([cs["write"]["clat_ns"]["mean"] for cs in client_stats.values()])
        avg_write_latency = sum(client_write_latencies) / len(client_write_latencies)

        # print(num_clients, total_read_iops, avg_read_latency, total_write_iops, avg_write_latency)
        yield {
            "mount_path": data["mount_path"],
            "mode": data["mode"],
            "block_size": data["block_size"],
            "io_depth": data["io_depth"] if "io_depth" in data else 0,
            "unique_filenames": data["unique_filenames"] if "unique_filenames" in data else True,
            "files_per_client": data["files_per_client"] if "files_per_client" in data else 1,
            "iteration": data["iteration"],
            "num_clients": num_clients,
            "total_read_iops": total_read_iops,
            "total_write_iops": total_write_iops,
            "avg_read_latency": avg_read_latency,
            "avg_write_latency": avg_write_latency
        }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Evaluate a file system")
    parser.add_argument("--results", required=True,
        help="directory for results")
    parser.add_argument("--scan-invocation-id",
        help="analyze just one scan")
    parser.add_argument("--output",
        help="output file for results")
    parser.add_argument("--max-missing", type=int, default=0,
        help="maximum number of missing results allowed")
    args = parser.parse_args()

    results_path = args.results
    if args.scan_invocation_id:
        a = analyze_scan(results_path, "scan-%s.json" % args.scan_invocation_id, args.max_missing)
        if args.output:
            print("output to %s" % args.output)
            with open(args.output, "w") as f:
                json.dump(list(a), f)
        else:
            for x in a:
                print(x)
    else:
        for fn in [f for f in os.listdir(results_path) if re.match("scan-[0-9a-f]{16}\.json", f)]:
            print(fn)
            analyze_scan(results_path, fn, args.max_missing)

# def analyze(data_fn):
#     #print(data_fn)
#     hostp = re.compile('^host.*')
#     with open(data_fn) as f:
#         jsonlines = [l for l in f.readlines() if not hostp.match(l)]
#         jsontext = "".join(jsonlines)
#         data = json.loads(jsontext)
#         #print(len(data["client_stats"]))
        # num_clients = len(client_stats)
        # client_iops = list([cs["read"]["iops_mean"] for cs in client_stats.values()])
        # total_iops = sum(client_iops)
        # client_latencies = list([cs["read"]["clat_ns"]["mean"] for cs in client_stats.values()])
        # avg_latency = sum(client_latencies) / len(client_latencies)
#         #print(total_iops, "%.1f" % (avg_latency / 1000000))
#         hostnames = list([cs["hostname"] for cs in client_stats.values()])
#     return num_clients, total_iops, avg_latency

# if __name__ == "__main__":
#     files = [fn for fn in os.listdir(".") if fnmatch.fnmatch(fn,"res_*.json")]
#     files.sort()
#     for fn in files:
#         print("%d %d %d" % analyze(fn))
